# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from anki import speedrun_pb2
from anki.speedrun import (
    expected_subtopic_tags,
    load_topics,
    subtopic_weights,
    unit_weights,
)
from tests.shared import getEmptyCol


def test_subtopic_weights_sum_to_unit_midpoints():
    # Per-subtopic importance weights are editable emphasis estimates, but they
    # stay grounded in the official section weights: each unit's subtopic weights
    # must sum to that unit's published midpoint (so the whole syllabus sums to
    # ~100). This guards against the emphasis silently drifting from the exam.
    topics = load_topics()
    sw = dict(subtopic_weights(topics))
    assert len(sw) == len(expected_subtopic_tags(topics))
    assert all(w > 0 for w in sw.values()), "every subtopic needs a positive weight"

    midpoints = dict(unit_weights(topics))
    for unit in topics["units"]:
        total = sum(float(s["weight"]) for s in unit["subtopics"])
        assert abs(total - midpoints[unit["id"]]) < 1e-9, unit["id"]


def test_speedrun_ping_end_to_end():
    # The trivial SpeedrunPing RPC proves the proto -> Rust -> Python plumbing
    # works end to end (new protobuf message called from Python).
    col = getEmptyCol()
    resp = col._backend.speedrun_ping()
    assert resp.marker.startswith("speedrun-ok:")
    assert resp.engine_version
    assert resp.marker == f"speedrun-ok:{resp.engine_version}"


def test_compute_readiness_gives_up_below_threshold():
    # The give-up rule is enforced in Rust and surfaced to Python: an empty
    # collection is below the >=200 reviews / >=50% coverage threshold, so the
    # oneof must be NoScore, never a fabricated number.
    col = getEmptyCol()
    units = [
        speedrun_pb2.UnitWeight(unit_id=uid, weight=w) for uid, w in unit_weights()
    ]
    result = col._backend.compute_readiness(
        expected_subtopics=expected_subtopic_tags(),
        units=units,
    )
    assert result.WhichOneof("value") == "no_score"
    assert result.no_score.graded_reviews == 0
    assert result.no_score.reviews_needed == 200
    assert result.no_score.coverage_pct == 0.0
    assert result.no_score.next_best_action
