# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from anki.speedrun import expected_subtopic_tags
from tests.shared import getEmptyCol


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
    result = col._backend.compute_readiness(
        expected_subtopics=expected_subtopic_tags()
    )
    assert result.WhichOneof("value") == "no_score"
    assert result.no_score.graded_reviews == 0
    assert result.no_score.reviews_needed == 200
    assert result.no_score.coverage_pct == 0.0
    assert result.no_score.next_best_action
