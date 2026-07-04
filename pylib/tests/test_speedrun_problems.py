# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Offline tests for exam-style problem generation (Phase 2).

These never call a model: they cover the deterministic templated generator, the
answer-matching used by self-verification, the quarantined pool, and the AI
off-switch behaviour (templated-only, no model calls, when AI is off). The live
AI path is exercised by ``tools/speedrun/evals/problem_eval.py`` when a key is
present.
"""

from __future__ import annotations

import os
import tempfile

import anki.collection  # noqa: F401
from anki.collection import Collection


def _fresh_col() -> Collection:
    """A collection in its OWN temp dir, so the sidecar pool file
    (``speedrun_generated_problems.json``, named next to the collection) is
    isolated per test — mirroring real profiles, which each have their own dir."""
    return Collection(os.path.join(tempfile.mkdtemp(), "col.anki2"))
from anki.speedrun.problem_gen import (
    _parse_num,
    answers_match,
    generate_verified_problems,
    load_pool,
    prebuild_templated_bank,
    save_to_pool,
    templated_problems,
)
from anki.speedrun.seed import build_deck


def test_templated_problems_are_correct_by_construction():
    ps = templated_problems("subtopic::univariate::variance", 3, seed=1)
    assert ps
    for p in ps:
        assert p.verified  # correct by construction
        assert p.model == "templated-baseline"
        assert p.source_name and p.question and p.solution
    # combinatorics answers are integers C(n, k).
    combos = templated_problems("subtopic::general::combinatorics", 2)
    assert combos and all(float(p.final_answer).is_integer() for p in combos)


def test_templated_is_deterministic_given_seed():
    a = templated_problems("subtopic::univariate::discrete_dists", 3, seed=7)
    b = templated_problems("subtopic::univariate::discrete_dists", 3, seed=7)
    assert [p.question for p in a] == [p.question for p in b]


def test_templated_covers_only_subtopics_with_a_template():
    # No template for this subtopic yet -> empty (the AI path covers it instead).
    assert templated_problems("subtopic::univariate::insurance_apps", 3) == []
    assert templated_problems("subtopic::univariate::discrete_dists", 2)


def test_answers_match_numeric_and_text():
    assert answers_match("0.45", "9/20")  # fraction == decimal
    assert answers_match("0.45", "0.451")  # within tolerance
    assert answers_match("45%", "0.45")  # percent == decimal
    assert answers_match("2/3", "0.667")
    assert not answers_match("0.45", "0.6")
    assert not answers_match("np", "n times p")  # different text, no number


def test_parse_num():
    assert _parse_num("45%") == 0.45
    assert _parse_num("9/20") == 0.45
    assert _parse_num("0.5") == 0.5
    assert _parse_num("no number here") is None


def test_pool_round_trip_and_dedupe():
    col = _fresh_col()
    try:
        ps = templated_problems("subtopic::univariate::variance", 2, seed=2)
        assert save_to_pool(col, ps) == len(ps)
        loaded = load_pool(col)
        assert {p.id for p in loaded} == {p.id for p in ps}
        # Re-adding the same problems is idempotent.
        assert save_to_pool(col, ps) == 0
    finally:
        col.close()


def test_prebuild_templated_bank_populates_pool_offline_and_is_idempotent():
    # The pre-built bank a practice test draws from: deterministic templated
    # (randomized-number) problems for every subtopic that has a template, saved
    # to the quarantined pool. Pure math (no AI), so it runs offline, and
    # re-running adds nothing (de-duped by id).
    col = _fresh_col()
    try:
        added = prebuild_templated_bank(col, per_subtopic=8, seed=0)
        assert added > 0
        pool = load_pool(col)
        assert len(pool) == added
        # Every banked problem is a source-stamped, verified templated item —
        # never mixed into the held-out corpus (its ids are the "gen-" namespace).
        assert all(p.model == "templated-baseline" and p.verified for p in pool)
        assert all(p.source_name for p in pool)
        # Idempotent: a second warm-up with the same params adds nothing.
        assert prebuild_templated_bank(col, per_subtopic=8, seed=0) == 0
        assert len(load_pool(col)) == added
    finally:
        col.close()


def test_generation_runs_offline_with_templates_when_ai_off():
    col = Collection(tempfile.mktemp(suffix=".anki2"))
    try:
        build_deck(col)  # AI is OFF by default
        # Decoupled: the TEMPLATED generator is plain math, not AI, so it runs with
        # the off-switch engaged and makes NO model calls (true even if a key is in
        # the env, because ai_enabled is False). A subtopic with a template yields
        # correct-by-construction templated problems…
        ps = generate_verified_problems(col, "subtopic::univariate::discrete_dists", 2)
        assert ps and all(p.model == "templated-baseline" for p in ps)
        # …and a subtopic WITHOUT a template yields nothing while AI is off (the AI
        # path would cover it, but the off-switch forbids model calls).
        assert generate_verified_problems(col, "subtopic::general::bayes", 1) == []
    finally:
        col.close()
