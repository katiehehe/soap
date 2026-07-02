# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import pytest

from anki import speedrun_pb2
from anki.speedrun import expected_subtopic_tags, unit_weights
from anki.speedrun.ai import (
    AiDisabledError,
    ai_enabled,
    require_ai,
    set_ai_enabled,
)
from tests.shared import getEmptyCol


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
