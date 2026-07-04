# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Schema tests for the committed AI-eval artifact builder (ai_eval.py).

These exercise the pure wrapper/writer only (no key, no network): they assert
the artifact shape and — the honesty-critical part — that AI cells stay null /
"pending" and ``ai_ran`` stays false unless an eval actually ran the AI side.
The heavy per-eval collection is exercised by running the eval scripts.
"""

from __future__ import annotations

import json
import os
import tempfile

from anki.speedrun.ai_eval import (
    SCHEMA_VERSION,
    build_report,
    write_report,
)

# A per-eval record as produced offline (no key): baseline filled, AI pending.
_PENDING_EVAL = {
    "name": "Feature X",
    "baseline_vs": "keyword",
    "baseline": {"top1": 0.13, "wrong_rate_top1": 0.87},
    "ai": None,
    "ai_ran": False,
    "verdict": "pending: run with OPENAI_API_KEY",
}

# A per-eval record as it would look after a keyed SUBSAMPLE (smoke) run.
_RAN_EVAL = {
    "name": "Feature Y",
    "baseline_vs": "extraction",
    "baseline": {"correct_rate": 0.30, "wrong_rate": 0.70},
    "ai": {
        "provider": "openai:gpt-4o-mini",
        "model": "gpt-4o-mini",
        "is_subsample": True,
        "sample_size": 15,
        "correct_rate": 0.92,
        "wrong_rate": 0.08,
    },
    "ai_ran": True,
    "verdict": "PASS on sample n=15",
}


def test_report_schema_and_metadata():
    report = build_report(
        {"a": dict(_PENDING_EVAL)}, git_sha="deadbee", generated_at=1_700_000_000
    )
    for key in (
        "schema_version",
        "generated_at_unix",
        "generated_at_utc",
        "git_sha",
        "ai_ran",
        "is_subsample",
        "ai_provider",
        "ai_model",
        "seed",
        "note",
        "evals",
    ):
        assert key in report
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["git_sha"] == "deadbee"
    # Timestamp is pinned deterministically when passed.
    assert report["generated_at_unix"] == 1_700_000_000
    assert report["generated_at_utc"] == "2023-11-14T22:13:20Z"


def test_ai_cells_pending_when_nothing_ran():
    # The honesty guard: with no eval having run the AI side, the top-level
    # flags stay off/null and the eval's AI cell stays null — even though a
    # provider/model/seed were passed in.
    report = build_report(
        {"a": dict(_PENDING_EVAL)},
        ai_provider="openai:gpt-4o-mini",
        ai_model="gpt-4o-mini",
        seed=0,
    )
    assert report["ai_ran"] is False
    assert report["is_subsample"] is False
    assert report["ai_provider"] is None
    assert report["ai_model"] is None
    assert report["seed"] is None
    assert report["evals"]["a"]["ai"] is None
    assert "pending" in report["evals"]["a"]["verdict"].lower()


def test_ai_ran_flag_and_metadata_when_an_eval_ran():
    report = build_report(
        {"pending": dict(_PENDING_EVAL), "ran": dict(_RAN_EVAL)},
        ai_provider="openai:gpt-4o-mini",
        ai_model="gpt-4o-mini",
        seed=7,
    )
    # Derived from the per-eval cells: any eval running the AI side flips it on.
    assert report["ai_ran"] is True
    assert report["ai_provider"] == "openai:gpt-4o-mini"
    assert report["ai_model"] == "gpt-4o-mini"
    assert report["seed"] == 7
    # is_subsample is DERIVED from the AI cells, not trusted from a flag.
    assert report["is_subsample"] is True
    assert report["evals"]["ran"]["ai"]["correct_rate"] == 0.92
    assert report["evals"]["pending"]["ai"] is None  # untouched


def test_full_run_is_not_flagged_subsample():
    # A keyed run whose AI cell is NOT a subsample must not be flagged as one.
    full = dict(_RAN_EVAL)
    full["ai"] = dict(_RAN_EVAL["ai"], is_subsample=False)
    report = build_report(
        {"ran": full}, ai_provider="openai:gpt-4o-mini", ai_model="gpt-4o-mini"
    )
    assert report["ai_ran"] is True
    assert report["is_subsample"] is False


def test_write_report_roundtrips_and_creates_dir():
    report = build_report({"a": dict(_PENDING_EVAL)}, generated_at=1_700_000_000)
    d = tempfile.mkdtemp()
    path = os.path.join(d, "nested", "ai_eval.json")
    written = write_report(report, path)
    assert os.path.exists(written)
    text = open(written, encoding="utf-8").read()
    assert text.endswith("\n")
    assert json.loads(text) == report
