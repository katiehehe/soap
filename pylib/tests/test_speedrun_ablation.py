# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Tests for the study-feature ablation (section 8). The harness must be FAIR:
equal study time across builds, and no separation unless an effect is assumed."""

from anki.speedrun.ablation import (
    BUILDS,
    build_sequence,
    evaluate_all,
    rep_counts,
    within_unit_interleaving,
)
from anki.speedrun.persona import synthetic_cohort
from anki.speedrun.soa_sample import load_sample_items


def test_equal_study_time_across_builds():
    # Every build studies the identical multiset of reps — only order differs.
    counts = {b: rep_counts(build_sequence(b)) for b in BUILDS}
    ref = counts["full"]
    for b in BUILDS:
        assert counts[b] == ref, b
    # And the total length matches.
    lengths = {len(build_sequence(b)) for b in BUILDS}
    assert len(lengths) == 1


def test_interleaving_exposure_orders_full_ablated_plain():
    scores = {b: within_unit_interleaving(build_sequence(b)) for b in BUILDS}
    assert scores["full"] > scores["ablated"] > scores["plain"]
    # Plain (fully blocked) has far less within-unit interleaving than Full
    # (its only same-unit adjacencies are the block boundaries).
    assert scores["plain"] < 0.5 * scores["full"]


def test_null_when_no_effect_assumed():
    # disc_gain = 0 removes the only build-dependent term: the builds MUST coincide.
    cohort = synthetic_cohort(30, seed=0)
    items = load_sample_items()
    res = evaluate_all(cohort, items, disc_gain=0.0)
    means = [res[b].accuracy_mean for b in BUILDS]
    assert max(means) - min(means) < 1e-9


def test_effect_orders_builds_when_assumed():
    # With a positive assumed effect, Full >= Ablated >= Plain, and Full beats
    # Plain strictly. This is the direction the mechanism implies, not a claim.
    cohort = synthetic_cohort(40, seed=0)
    items = load_sample_items()
    res = evaluate_all(cohort, items, disc_gain=1.5)
    full = res["full"].accuracy_mean
    ablated = res["ablated"].accuracy_mean
    plain = res["plain"].accuracy_mean
    assert full >= ablated >= plain
    assert full > plain


def test_deterministic():
    cohort = synthetic_cohort(25, seed=7)
    items = load_sample_items()
    a = evaluate_all(cohort, items, disc_gain=1.0)
    b = evaluate_all(cohort, items, disc_gain=1.0)
    assert [a[x].accuracy_mean for x in BUILDS] == [b[x].accuracy_mean for x in BUILDS]
