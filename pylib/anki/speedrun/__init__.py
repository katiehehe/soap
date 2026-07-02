# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""SOA Exam P "Speedrun" study data owned by the Python side.

The official Exam P topic map lives in ``exam_p_topics.json`` and is the single
source of truth for coverage and for the tags the mastery-gated scheduler gates
on. The Rust readiness RPC receives the expected-subtopic list from here, so the
curriculum is never hardcoded in the engine.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_TOPICS_PATH = Path(__file__).parent / "exam_p_topics.json"


def load_topics() -> dict[str, Any]:
    """Return the parsed Exam P topic map."""
    with open(_TOPICS_PATH, encoding="utf8") as file:
        return json.load(file)


def unit_tag(unit_id: str) -> str:
    return f"unit::{unit_id}"


def subtopic_tag(unit_id: str, subtopic_id: str) -> str:
    return f"subtopic::{unit_id}::{subtopic_id}"


def difficulty_tag(level: str) -> str:
    return f"difficulty::{level}"


def unit_weights(topics: dict[str, Any] | None = None) -> list[tuple[str, float]]:
    """Relative per-unit weights: the midpoint of each published SOA section range.

    Passed to the readiness RPC so coverage is weighted by the real exam weights.
    """
    topics = topics or load_topics()
    weights: list[tuple[str, float]] = []
    for unit in topics["units"]:
        low, high = unit["weight_pct"]
        weights.append((unit["id"], (low + high) / 2.0))
    return weights


def expected_subtopic_tags(topics: dict[str, Any] | None = None) -> list[str]:
    """Every subtopic tag in the syllabus (the denominator for coverage)."""
    topics = topics or load_topics()
    tags: list[str] = []
    for unit in topics["units"]:
        for subtopic in unit["subtopics"]:
            tags.append(subtopic_tag(unit["id"], subtopic["id"]))
    return tags


def unit_name(unit_id: str, topics: dict[str, Any] | None = None) -> str:
    topics = topics or load_topics()
    for unit in topics["units"]:
        if unit["id"] == unit_id:
            return unit["name"]
    raise KeyError(f"unknown unit: {unit_id}")


def subtopic_name(
    unit_id: str, subtopic_id: str, topics: dict[str, Any] | None = None
) -> str:
    topics = topics or load_topics()
    for unit in topics["units"]:
        if unit["id"] == unit_id:
            for subtopic in unit["subtopics"]:
                if subtopic["id"] == subtopic_id:
                    return subtopic["name"]
    raise KeyError(f"unknown subtopic: {unit_id}::{subtopic_id}")
