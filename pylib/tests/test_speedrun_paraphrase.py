# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Tests for the paraphrase test (challenge 7d): performance must not just copy
memory. The gap between card recall and reworded accuracy is the deliverable."""

import random

from anki.speedrun import expected_subtopic_tags
from anki.speedrun.paraphrase import (
    COPYING_GAP,
    ParaphraseCard,
    grade,
    load_paraphrase_cards,
    reworded_distinctness,
)
from anki.speedrun.persona import (
    p_correct,
    recall_prob,
    response_time_for,
    synthetic_cohort,
)


def _simulate(cards, cohort, recall_fn, perf_fn, seed=0):
    """Minimal deterministic cohort simulation (mirrors the eval runner) so the
    bridge property can be asserted without shelling out to the CLI."""
    from dataclasses import replace

    pseudo = []
    recalls = {}
    reworded = {}
    for persona in cohort:
        cov = min(1.0, max(0.4, sum(persona.skill.values()) / len(persona.skill)))
        for card in cards:
            cid = f"{persona.name}|{card.id}"
            pseudo.append(replace(card, id=cid))
            rng = random.Random(f"recall|{persona.seed}|{card.id}|{seed}")
            recalls[cid] = 1 if rng.random() < recall_fn(persona, card, cov) else 0
            outs = []
            for i in range(len(card.reworded)):
                rng2 = random.Random(f"reword|{persona.seed}|{card.id}|{i}|{seed}")
                outs.append(1 if rng2.random() < perf_fn(persona, card, cov) else 0)
            reworded[cid] = outs
    return grade(pseudo, recalls, reworded)


def _memory(persona, card, cov):
    return recall_prob(persona, card.subtopic)


def _perf(persona, card, cov):
    rt = response_time_for(persona, card.subtopic, card.difficulty)
    return p_correct(persona, card.subtopic, card.difficulty, cov, rt)


def test_dataset_has_30_cards_each_with_two_rewordings():
    cards = load_paraphrase_cards()
    assert len(cards) >= 30
    valid = set(expected_subtopic_tags())
    for c in cards:
        assert len(c.reworded) == 2, c.id
        assert c.subtopic in valid, c.subtopic
        assert c.card_prompt and c.fact
        assert all(q.strip() for q in c.reworded)


def test_rewordings_are_distinct_from_the_card_prompt():
    # Every reworded question must differ enough from its memory prompt, or
    # "performance" would just be a re-read of the card (data-level copying).
    assert reworded_distinctness(load_paraphrase_cards()) == []


def test_grade_computes_rates_and_gap():
    cards = [
        ParaphraseCard(
            id="c1",
            subtopic="subtopic::general::sets_axioms",
            difficulty="easy",
            fact="f",
            card_prompt="p",
            reworded=["q1", "q2"],
        )
    ]
    # Recalled the card, missed both reworded questions -> maximal gap.
    res = grade(cards, {"c1": 1}, {"c1": [0, 0]})
    assert res.recall_rate == 1.0
    assert res.reworded_rate == 0.0
    assert res.gap == 1.0
    assert not res.copying


def test_persona_shows_a_real_bridge():
    # Memory recall should clearly exceed reworded accuracy: performance is a
    # separate, harder signal (the bridge exists).
    cohort = synthetic_cohort(40, seed=0)
    cards = load_paraphrase_cards()
    res = _simulate(cards, cohort, _memory, _perf, seed=0)
    assert res.recall_rate > res.reworded_rate
    assert res.gap > COPYING_GAP
    assert not res.copying
    assert "BRIDGE" in res.verdict


def test_copycat_control_is_flagged_as_copying():
    # Feeding the performance model into BOTH sides collapses the gap: the test
    # must catch a performance signal that merely tracks memory.
    cohort = synthetic_cohort(40, seed=0)
    cards = load_paraphrase_cards()
    res = _simulate(cards, cohort, _perf, _perf, seed=0)
    assert abs(res.gap) < COPYING_GAP
    assert res.copying
    assert "COPYING" in res.verdict


def test_simulation_is_deterministic():
    cohort = synthetic_cohort(20, seed=3)
    cards = load_paraphrase_cards()
    a = _simulate(cards, cohort, _memory, _perf, seed=3)
    b = _simulate(cards, cohort, _memory, _perf, seed=3)
    assert (a.recall_correct, a.reworded_correct) == (
        b.recall_correct,
        b.reworded_correct,
    )
