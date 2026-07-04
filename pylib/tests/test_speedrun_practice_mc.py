# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Multiple-choice parsing + objective grading for the practice test."""

from anki.speedrun.practice_test import (
    correct_letter,
    free_response_correct,
    is_mcq,
    parse_choices,
)
from anki.speedrun.soa_sample import SampleItem


def test_parse_choices_splits_stem_and_options():
    q = "Calculate the percentage. (A) 24% (B) 36% (C) 41% (D) 52% (E) 60%"
    stem, choices = parse_choices(q)
    assert stem == "Calculate the percentage."
    assert choices == [
        ("A", "24%"),
        ("B", "36%"),
        ("C", "41%"),
        ("D", "52%"),
        ("E", "60%"),
    ]


def test_parse_choices_ignores_non_choice_parens():
    # "f(x)" and "(0, 40)" must not be mistaken for option markers.
    q = "For f(x) on (0, 40), find P. (A) 0.1 (B) 0.2 (C) 0.3 (D) 0.4 (E) 0.5"
    stem, choices = parse_choices(q)
    assert stem == "For f(x) on (0, 40), find P."
    assert [c[0] for c in choices] == ["A", "B", "C", "D", "E"]


def test_parse_choices_empty_for_free_response():
    stem, choices = parse_choices("How many arrangements of the word LEVEL?")
    assert choices == []
    assert stem == "How many arrangements of the word LEVEL?"


def test_correct_letter():
    assert correct_letter("D) 52%") == "D"
    assert correct_letter("(A) 0.05") == "A"
    # Free-response answers are not A-E choices.
    assert correct_letter("Exponential(1)") is None
    assert correct_letter("0.45") is None
    assert correct_letter("9/20 = 0.45") is None


def test_free_response_correct_numeric_and_string():
    assert free_response_correct("0.45", "9/20 = 0.45")
    assert free_response_correct("0.30", "0.3")
    assert free_response_correct("45%", "0.45")
    assert not free_response_correct("0.9", "0.3")
    # An empty response is never correct.
    assert not free_response_correct("", "0.3")


def _item(question: str, answer: str) -> SampleItem:
    return SampleItem(
        id="x",
        question=question,
        subtopic="subtopic::general::sets_axioms",
        difficulty="medium",
        answer=answer,
    )


def test_is_mcq_accepts_embedded_and_numeric_items():
    # Embedded (A)-(E) options -> multiple choice.
    assert is_mcq(_item("Find P. (A) 0.1 (B) 0.2 (C) 0.3 (D) 0.4 (E) 0.5", "C) 0.3"))
    # A numeric answer with no embedded options is still MC (distractors are
    # synthesised around it).
    assert is_mcq(_item("How many committees of 3 from 8?", "56"))
    assert is_mcq(_item("Find P(A|B).", "0.45"))


def test_is_mcq_rejects_non_numeric_free_response():
    # No embedded options and a non-numeric answer cannot become A-E choices, so
    # the assembler drops it (a test must be 100% multiple choice).
    assert not is_mcq(_item("Name the distribution.", "Exponential"))
    assert not is_mcq(_item("Give the pmf.", "p(x) = e^-l l^x / x!"))
