# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Practice-test mode: timed, exam-shaped tests that drive the Readiness signal.

Per ``docs/vision.md``, readiness is driven by full practice tests, not review
counts. A test is assembled from the HELD-OUT exam-style corpus
(``soa_sample``), mixed across the three units by the official SOA section
weights (General 23-30%, Univariate 44-50%, Multivariate 23-30%). Grading a test
accumulates ``{questions, correct, tests}`` into collection config
(``speedrunPracticeStats``), which the Rust ``compute_readiness`` reads to emit a
readiness band — still behind the give-up rule.

Honesty: practice items are held-out evaluation only (never AI training), and the
stored counts are real graded results (from a real student, or the clearly
labelled synthetic persona). Nothing here fabricates a score; it records graded
outcomes that the engine turns into a range.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from anki.speedrun import unit_weights
from anki.speedrun.soa_sample import SampleItem, load_sample_items

if TYPE_CHECKING:
    from anki.collection import Collection

# Collection-config keys. Mirrored in rslib/src/speedrun/{service,mastery}.rs.
PRACTICE_STATS_KEY = "speedrunPracticeStats"  # {"questions", "correct", "tests"}
PRACTICE_LOG_KEY = "speedrunPracticeLog"  # list of per-test summaries (audit)
# Per-subtopic performance from practice tests: {tag: {"questions", "correct"}}.
# A SEPARATE signal from the memory gate (never blended); it can satisfy
# prerequisites in the guided DAG and is shown next to mastery on the map.
PERFORMANCE_KEY = "speedrunPerformanceBySubtopic"

DEFAULT_TEST_SIZE = 30


@dataclass(frozen=True)
class TestResult:
    questions: int
    correct: int
    per_unit: dict[str, tuple[int, int]]  # unit_id -> (correct, total)
    per_subtopic: dict[str, tuple[int, int]]  # subtopic tag -> (correct, total)
    label: str = ""

    @property
    def proportion(self) -> float:
        return self.correct / self.questions if self.questions else 0.0


def _unit_allocation(n: int, topics: dict[str, Any] | None = None) -> dict[str, int]:
    """Split ``n`` questions across units by section-weight midpoints, summing to
    exactly ``n`` (largest-remainder rounding so nothing is lost)."""
    weights = unit_weights(topics)
    total_w = sum(w for _, w in weights) or 1.0
    raw = [(uid, n * w / total_w) for uid, w in weights]
    floors = {uid: int(x) for uid, x in raw}
    allocated = sum(floors.values())
    remainder = sorted(raw, key=lambda t: t[1] - int(t[1]), reverse=True)
    i = 0
    while allocated < n and remainder:
        uid = remainder[i % len(remainder)][0]
        floors[uid] += 1
        allocated += 1
        i += 1
    return floors


def assemble_test(
    n: int = DEFAULT_TEST_SIZE,
    seed: int = 0,
    items: list[SampleItem] | None = None,
    topics: dict[str, Any] | None = None,
) -> list[SampleItem]:
    """Assemble a section-weighted test of ``n`` items from the held-out corpus.

    Deterministic given the seed. Samples without replacement within a unit when
    possible; if a unit has fewer items than its allocation, it takes all of them
    and the shortfall is filled from the remaining pool, so the test is always
    exam-shaped and reproducible.
    """
    pool = items if items is not None else load_sample_items()
    by_unit: dict[str, list[SampleItem]] = {}
    for it in pool:
        by_unit.setdefault(it.unit_id, []).append(it)

    alloc = _unit_allocation(n, topics)
    rng = random.Random(seed)
    chosen: list[SampleItem] = []
    for uid, count in alloc.items():
        bucket = sorted(by_unit.get(uid, []), key=lambda it: it.id)
        rng.shuffle(bucket)
        chosen.extend(bucket[:count])

    # Fill any shortfall (a thin unit) from the rest of the pool, deterministically.
    if len(chosen) < n:
        chosen_ids = {it.id for it in chosen}
        rest = sorted(
            (it for it in pool if it.id not in chosen_ids), key=lambda it: it.id
        )
        rng.shuffle(rest)
        chosen.extend(rest[: n - len(chosen)])

    rng.shuffle(chosen)
    return chosen[:n]


def grade(
    items: list[SampleItem], responses: dict[str, int], label: str = ""
) -> TestResult:
    """Grade a test: ``responses`` maps item id -> 1 (correct) / 0 (wrong).
    Missing responses count as wrong. Reports the per-unit breakdown too."""
    per_unit: dict[str, list[int]] = {}
    per_sub: dict[str, list[int]] = {}
    correct = 0
    for it in items:
        got = 1 if responses.get(it.id, 0) == 1 else 0
        correct += got
        cell = per_unit.setdefault(it.unit_id, [0, 0])
        cell[0] += got
        cell[1] += 1
        scell = per_sub.setdefault(it.subtopic, [0, 0])
        scell[0] += got
        scell[1] += 1
    return TestResult(
        questions=len(items),
        correct=correct,
        per_unit={u: (c, t) for u, (c, t) in per_unit.items()},
        per_subtopic={s: (c, t) for s, (c, t) in per_sub.items()},
        label=label,
    )


def practice_stats(col: Collection) -> dict[str, int]:
    """Accumulated practice-test evidence from config (empty when none taken)."""
    stats = col.get_config(PRACTICE_STATS_KEY, None) or {}
    return {
        "questions": int(stats.get("questions", 0)),
        "correct": int(stats.get("correct", 0)),
        "tests": int(stats.get("tests", 0)),
    }


def performance_by_subtopic(col: Collection) -> dict[str, dict[str, int]]:
    """Accumulated per-subtopic practice-test performance from config
    (tag -> {questions, correct}). Empty when no tests have been graded."""
    raw = col.get_config(PERFORMANCE_KEY, None) or {}
    out: dict[str, dict[str, int]] = {}
    for tag, cell in raw.items():
        out[tag] = {
            "questions": int(cell.get("questions", 0)),
            "correct": int(cell.get("correct", 0)),
        }
    return out


def record_test(col: Collection, result: TestResult) -> dict[str, int]:
    """Accumulate a graded test into collection config so the readiness engine
    can read it. Returns the new running totals. Appends a small audit summary.
    Also accumulates per-subtopic PERFORMANCE (a separate signal from the memory
    gate) that can satisfy prerequisites in the guided DAG."""
    stats = practice_stats(col)
    stats["questions"] += result.questions
    stats["correct"] += result.correct
    stats["tests"] += 1
    col.set_config(PRACTICE_STATS_KEY, stats)

    perf = performance_by_subtopic(col)
    for tag, (c, t) in result.per_subtopic.items():
        cell = perf.setdefault(tag, {"questions": 0, "correct": 0})
        cell["questions"] += t
        cell["correct"] += c
    col.set_config(PERFORMANCE_KEY, perf)

    log = col.get_config(PRACTICE_LOG_KEY, None) or []
    log.append(
        {
            "at": int(time.time()),
            "questions": result.questions,
            "correct": result.correct,
            "proportion": round(result.proportion, 4),
            "per_unit": {u: list(v) for u, v in result.per_unit.items()},
            "label": result.label,
        }
    )
    col.set_config(PRACTICE_LOG_KEY, log)
    return stats


def reset_practice_stats(col: Collection) -> None:
    """Clear stored practice-test evidence (readiness returns to abstaining)."""
    col.remove_config(PRACTICE_STATS_KEY)
    col.remove_config(PRACTICE_LOG_KEY)
    col.remove_config(PERFORMANCE_KEY)
