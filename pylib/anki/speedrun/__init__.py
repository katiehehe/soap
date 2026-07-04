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
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

_TOPICS_PATH = Path(__file__).parent / "exam_p_topics.json"

# Config key holding the target exam date (unix seconds, local noon of the day).
# Mirrors EXAM_DATE_KEY in rslib/src/speedrun/mastery.rs.
EXAM_DATE_KEY = "speedrunExamDate"


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


def subtopic_weights(topics: dict[str, Any] | None = None) -> list[tuple[str, float]]:
    """Relative per-subtopic importance weights, keyed by subtopic tag.

    These are editable emphasis estimates (see ``weights_note`` in the topic
    map), not official SOA figures: SOA publishes weights only at the unit level,
    so each unit's subtopic weights are authored to sum to that unit's published
    section midpoint. Passed to the mastery RPC so the engine can compute an
    importance-weighted mastery rollup, and used by the study map to size each
    subtopic bubble. They never affect the honesty/give-up thresholds.
    """
    topics = topics or load_topics()
    weights: list[tuple[str, float]] = []
    for unit in topics["units"]:
        for subtopic in unit["subtopics"]:
            weights.append(
                (subtopic_tag(unit["id"], subtopic["id"]), float(subtopic["weight"]))
            )
    return weights


def deck_name_for_subtopic_tag(
    tag: str, root: str = "SOA Exam P", topics: dict[str, Any] | None = None
) -> str | None:
    """Deck name for a ``subtopic::<unit>::<sub>`` tag, matching how ``build_deck``
    names its subdecks (``root::unit name::subtopic name``).

    Used to open a subtopic's deck for blocked practice from the study map.
    Returns None for a malformed or unknown tag.
    """
    parts = tag.split("::")
    if len(parts) != 3 or parts[0] != "subtopic":
        return None
    _, unit_id, subtopic_id = parts
    topics = topics or load_topics()
    try:
        return "::".join(
            [
                root,
                unit_name(unit_id, topics),
                subtopic_name(unit_id, subtopic_id, topics),
            ]
        )
    except KeyError:
        return None


def unit_deck_name(
    unit_id: str, root: str = "SOA Exam P", topics: dict[str, Any] | None = None
) -> str | None:
    """Deck name for a unit (``root::unit name``), used to open a unit's deck for
    within-unit interleaving. Returns None for an unknown unit."""
    topics = topics or load_topics()
    try:
        return "::".join([root, unit_name(unit_id, topics)])
    except KeyError:
        return None


def exam_timestamp_for_iso(iso: str) -> int | None:
    """Unix seconds at local noon of an ISO ``YYYY-MM-DD`` exam date, or None if
    it can't be parsed. Noon (not midnight) so the whole-days-left count the
    engine computes is robust to timezones and Anki's day rollover.
    """
    try:
        day = date.fromisoformat(iso.strip())
    except (ValueError, AttributeError):
        return None
    return int(datetime.combine(day, time(12, 0)).timestamp())


def set_exam_date(col: Any, iso: str) -> bool:
    """Store the target exam date (from an ISO ``YYYY-MM-DD`` string) so the
    engine can report coverage pace. Returns False if the date is unparseable.
    Only affects the pace read-out; never touches any score or the give-up rule.
    """
    ts = exam_timestamp_for_iso(iso)
    if ts is None:
        return False
    col.set_config(EXAM_DATE_KEY, ts)
    return True


def clear_exam_date(col: Any) -> None:
    """Remove the stored exam date (pace goes back to 'no deadline set')."""
    col.remove_config(EXAM_DATE_KEY)


def exam_date_iso(col: Any) -> str | None:
    """The stored exam date as an ISO ``YYYY-MM-DD`` string, or None if unset."""
    ts = col.get_config(EXAM_DATE_KEY, None)
    if ts is None:
        return None
    return datetime.fromtimestamp(ts).date().isoformat()


def apply_subtopic_weights_config(
    col: Any, topics: dict[str, Any] | None = None
) -> None:
    """Write the per-subtopic importance weights to collection config.

    The engine's opt-in points-at-stake live review order reads these
    (``speedrunSubtopicWeights``) so it can weight by exam importance without a
    request round-trip. Weights only affect review *ordering*; they never touch
    the honesty/give-up thresholds or any score. Safe to call repeatedly.
    """
    weights = {tag: weight for tag, weight in subtopic_weights(topics)}
    col.set_config("speedrunSubtopicWeights", weights)


def subtopic_prereqs(
    topics: dict[str, Any] | None = None,
) -> list[tuple[str, list[str]]]:
    """Per-subtopic prerequisite tags for the guided-learning DAG, keyed by
    subtopic tag. Prereq ids in the topic map are within the same unit, so they
    resolve to ``subtopic::<unit>::<prereq>`` tags here."""
    topics = topics or load_topics()
    out: list[tuple[str, list[str]]] = []
    for unit in topics["units"]:
        for sub in unit["subtopics"]:
            prereq_tags = [
                subtopic_tag(unit["id"], pid) for pid in sub.get("prereqs", [])
            ]
            out.append((subtopic_tag(unit["id"], sub["id"]), prereq_tags))
    return out


def unit_prereqs(
    topics: dict[str, Any] | None = None,
) -> list[tuple[str, list[str]]]:
    """Per-unit prerequisite unit ids (the cross-unit curriculum order)."""
    topics = topics or load_topics()
    return [(unit["id"], list(unit.get("prereqs", []))) for unit in topics["units"]]


def apply_prereqs_config(col: Any, topics: dict[str, Any] | None = None) -> None:
    """Write the guided-learning DAG to collection config so the live queue gate
    can read it without a request round-trip. Curriculum order only; it never
    affects any score or the give-up rule. Safe to call repeatedly."""
    topics = topics or load_topics()
    col.set_config(
        "speedrunSubtopicPrereqs",
        {tag: prereqs for tag, prereqs in subtopic_prereqs(topics)},
    )
    col.set_config(
        "speedrunUnitPrereqs",
        {uid: prereqs for uid, prereqs in unit_prereqs(topics)},
    )


# Guided-learning gate config. Mirrors GUIDED_MODE_KEY / UNLOCKED_SUBTOPICS_KEY
# in rslib/src/speedrun/mastery.rs. Guided mode defaults ON (a fresh learner is
# guided through the curriculum order); turning it off is the free-mode bypass.
GUIDED_MODE_KEY = "speedrunGuidedMode"
UNLOCKED_SUBTOPICS_KEY = "speedrunUnlockedSubtopics"
# Mirrors MASTERY_SCHEDULER_KEY in rslib/src/speedrun/mastery.rs: the opt-in
# three-tier mastery scheduler (the live new-card tier order). Enabled on the
# seeded Exam P deck; the toggle lets the demo flip Full vs plain Anki.
MASTERY_SCHEDULER_KEY = "speedrunMasteryScheduler"


def guided_mode_enabled(col: Any) -> bool:
    """Whether the hard prerequisite gate is on (default True)."""
    return bool(col.get_config(GUIDED_MODE_KEY, True))


def mastery_scheduler_enabled(col: Any) -> bool:
    """Whether the three-tier mastery scheduler reorders the live queue (default
    False upstream; enabled on the seeded Exam P deck)."""
    return bool(col.get_config(MASTERY_SCHEDULER_KEY, False))


def set_mastery_scheduler(col: Any, on: bool) -> None:
    """Turn the three-tier mastery scheduler on/off. Ordering only (read-only
    reorder in build_queues); never changes FSRS intervals or any score."""
    col.set_config(MASTERY_SCHEDULER_KEY, bool(on))


def set_guided_mode(col: Any, on: bool) -> None:
    """Turn the guided prerequisite gate on/off (the global 'free mode' bypass).
    Curriculum ordering only — it never changes any score or the give-up rule."""
    col.set_config(GUIDED_MODE_KEY, bool(on))


def unlocked_subtopics(col: Any) -> list[str]:
    """Subtopic tags the user has explicitly unlocked (per-topic gate bypass)."""
    return list(col.get_config(UNLOCKED_SUBTOPICS_KEY, []) or [])


def unlock_subtopic(col: Any, tag: str) -> None:
    """Bypass the guided gate for one subtopic (for experienced users). Additive
    and idempotent; never touches memory/performance or the give-up rule."""
    cur = unlocked_subtopics(col)
    if tag and tag not in cur:
        cur.append(tag)
        col.set_config(UNLOCKED_SUBTOPICS_KEY, cur)


def relock_subtopic(col: Any, tag: str) -> None:
    """Undo a per-topic unlock (return it to the guided gate)."""
    cur = [t for t in unlocked_subtopics(col) if t != tag]
    col.set_config(UNLOCKED_SUBTOPICS_KEY, cur)


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
