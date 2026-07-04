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
import re
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

# A practice test comes in two shapes (both timed at the real exam's ~6 min per
# question pace; the timing is enforced client-side in the practice-test screen):
#   * FULL EXAM SIMULATION — the canonical, most-representative test: exactly
#     30 questions, section-weighted across the three units, timed for 3 hours.
#   * TOPIC / UNIT QUIZ — a shorter, scoped drill: 10 questions by default,
#     timed for 1 hour.
DEFAULT_TEST_SIZE = 30
FULL_EXAM_SIZE = 30
QUIZ_SIZE = 10

# --- Representativeness weight (readiness evidence) --------------------------
# Not every test is equally informative about exam readiness. A full, whole-exam
# test drawn from the OFFICIAL held-out corpus is the most representative, so its
# graded evidence counts fully (weight 1.0); a narrower scope or a generated
# source counts for proportionally less. record_test stores this weighted
# evidence ALONGSIDE the raw integer counts, and the Rust readiness engine uses
# the WEIGHTED proportion for the band while the give-up GATE still uses the raw
# question count. Tunable constants (see docs/score-models.md).
SCOPE_FACTORS: dict[str, float] = {"all": 1.0, "unit": 0.6, "subtopic": 0.4}
SOURCE_FACTORS: dict[str, float] = {"official": 1.0, "generated": 0.7}


def readiness_weight(scope: str, source: str) -> float:
    """Representativeness weight ``w = scope_factor x source_factor`` for a test.

    ``scope`` is ``"all"`` | ``"unit"`` | ``"subtopic"`` and ``source`` is
    ``"official"`` (held-out corpus) | ``"generated"`` (templated / verified-AI
    bank). A full, whole-exam official test scores 1.0; unknown values fall back
    to the most conservative factor so evidence is never over-counted.
    """
    scope_f = SCOPE_FACTORS.get(scope, SCOPE_FACTORS["subtopic"])
    source_f = SOURCE_FACTORS.get(source, SOURCE_FACTORS["generated"])
    return scope_f * source_f


# --- Multiple-choice parsing ------------------------------------------------
# The official SOA sample items embed their (A)-(E) options inline in the
# question text and put the correct letter first in `answer` (e.g. "D) 52%").
# We parse those into a stem + options so the UI can render real radio choices
# and grade objectively. Items with no (A)-(E) block (the committed original
# fallback corpus) return no choices, and the caller grades them by typed value.

# A genuine option marker "(A)", NOT preceded by a letter/digit — so probability
# notation like "P(A)", "P(B)", "P(A∪B)" is never mistaken for choice letters.
_CHOICE_RE = re.compile(r"(?<![A-Za-z0-9])\(([A-E])\)")


def parse_choices(question: str) -> tuple[str, list[tuple[str, str]]]:
    """Split a question into ``(stem, [(letter, text), ...])``.

    Finds the trailing run of ``(A) ... (B) ... (E)`` markers (letters
    consecutive from A) and splits the text there. Returns the whole question as
    the stem and an empty list when there is no such block.
    """
    start: int | None = None
    seq: list[re.Match[str]] = []
    for m in _CHOICE_RE.finditer(question):
        letter = m.group(1)
        if letter == "A":
            start, seq = m.start(), [m]
        elif seq and ord(letter) == ord(seq[-1].group(1)) + 1:
            seq.append(m)
        else:
            start, seq = None, []
    if start is None or len(seq) < 2:
        return question.strip(), []
    choices: list[tuple[str, str]] = []
    for i, m in enumerate(seq):
        text_start = m.end()
        text_end = seq[i + 1].start() if i + 1 < len(seq) else len(question)
        choices.append((m.group(1), question[text_start:text_end].strip()))
    return question[:start].strip(), choices


def correct_letter(answer: str) -> str | None:
    """The correct option letter parsed from an ``answer`` like ``"D) 52%"`` or
    ``"(D) 52%"``. Returns None when the answer is not an A-E choice (a
    free-response fallback item), so the caller can grade by value instead."""
    m = re.match(r"\s*\(?([A-E])\)", answer)
    return m.group(1) if m else None


def _to_number(s: str) -> float | None:
    """Best-effort parse of a final numeric answer: takes the last number token
    (usually the final value, e.g. "9/20 = 0.45" -> 0.45) and treats a trailing
    ``%`` as a fraction. None when nothing numeric is present."""
    nums = re.findall(r"[-+]?\d*\.?\d+%?", s.replace(",", ""))
    if not nums:
        return None
    tok = nums[-1]
    if tok.endswith("%"):
        return float(tok[:-1]) / 100.0
    return float(tok)


def free_response_correct(typed: str, answer: str, tol: float = 0.02) -> bool:
    """Grade a typed free-response answer (the choice-less fallback corpus):
    numeric match within a relative tolerance, else normalized string equality.
    Used only when an item has no (A)-(E) choices."""
    t, a = _to_number(typed), _to_number(answer)
    if t is not None and a is not None:
        return abs(t) < 1e-9 if a == 0 else abs(t - a) / abs(a) <= tol
    norm = re.sub(r"\s+", "", typed.strip().lower())
    return norm != "" and norm == re.sub(r"\s+", "", answer.strip().lower())


# --- Multiple-choice SYNTHESIS ----------------------------------------------
# The corpus items are free-response (a question + a numeric answer). To present
# EVERY item as real A-E multiple choice, we synthesise plausible numeric
# distractors around the correct value. Deterministic per item id, so assembly
# and grading always agree on the option letters.

_LETTERS = "ABCDE"


def answer_value(answer: str) -> float | None:
    """Numeric value of an answer, ignoring a leading option letter and any
    'x = ' prefix (e.g. "D) 52%" -> 0.52, "9/20 = 0.45" -> 0.45)."""
    s = re.sub(r"^\s*\(?[A-E]\)\s*", "", answer.strip())
    if "=" in s:
        s = s.split("=")[-1]
    return _to_number(s)


def _fmt_num(x: float) -> str:
    r = round(x, 4)
    return str(int(r)) if r == int(r) else f"{r:g}"


def _distractors(value: float, rng: random.Random, n: int) -> list[float]:
    """`n` plausible wrong numeric answers around `value`. Probabilities stay in
    [0, 1]; common-error values (complement, half, double) come first, then small
    signed offsets pad out any shortfall so we always return `n` of them."""
    is_prob = 0.0 <= value <= 1.0
    if is_prob:
        pool = [
            1 - value, value / 2, min(1.0, value * 2), value + 0.1, value - 0.1,
            value + 0.05, value - 0.05, min(1.0, value * 1.5),
        ]
    else:
        pool = [
            value * 2, value / 2, value + 1, value - 1, value * 1.5,
            value * 0.75, value + 2, abs(value) + 0.5,
        ]
    rng.shuffle(pool)
    # Deterministic small-offset padding (±0.01, ±0.02, …) guarantees enough
    # candidates even for edge values, in a single pass.
    pool += [value + 0.01 * step * sign for step in range(1, 60) for sign in (1, -1)]
    seen = {round(value, 4)}
    out: list[float] = []
    for cand in pool:
        r = round(cand, 4)
        if r in seen or (is_prob and not 0.0 <= r <= 1.0):
            continue
        seen.add(r)
        out.append(r)
        if len(out) >= n:
            break
    return out


def build_mcq(
    question: str, answer: str, item_id: str, n_options: int = 4
) -> tuple[str, list[tuple[str, str]], str | None]:
    """Turn any item into a real multiple-choice question: ``(stem, [(letter,
    text), ...], correct_letter)``. Uses genuine embedded (A)-(E) options when the
    item has them; otherwise synthesises plausible numeric distractors around the
    correct value. DETERMINISTIC per ``item_id`` so assembly and grading agree.
    Returns ``([], None)`` only when the answer is not numeric (a typed fallback)."""
    stem, embedded = parse_choices(question)
    letter = correct_letter(answer)
    if embedded and letter and any(ltr == letter for ltr, _ in embedded):
        return stem, embedded, letter
    value = answer_value(answer)
    if value is None:
        return question.strip(), [], None
    rng = random.Random(f"mcq:{item_id}")
    options = [(v, False) for v in _distractors(value, rng, max(1, n_options - 1))]
    options.append((round(value, 4), True))
    rng.shuffle(options)
    as_pct = "%" in answer

    def fmt(v: float) -> str:
        return f"{_fmt_num(v * 100)}%" if as_pct else _fmt_num(v)

    choices = [(_LETTERS[i], fmt(v)) for i, (v, _ok) in enumerate(options)]
    correct = next(_LETTERS[i] for i, (_v, ok) in enumerate(options) if ok)
    return question.strip(), choices, correct


def is_mcq(item: SampleItem) -> bool:
    """Whether an item can be presented as real A-E multiple choice.

    Every question in a practice test must be multiple choice (like the real
    exam), so the assembler filters the pool with this: an item qualifies when
    ``build_mcq`` yields genuine A-E options and a correct letter (true for any
    item with embedded (A)-(E) options or a numeric answer we can synthesise
    distractors around). Items that cannot become choices are dropped."""
    _stem, choices, correct = build_mcq(item.question, item.answer, item.id)
    return bool(choices) and correct is not None


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


def record_test(
    col: Collection,
    result: TestResult,
    scope: str = "all",
    source: str = "official",
) -> dict[str, float]:
    """Accumulate a graded test into collection config so the readiness engine
    can read it. Returns the new running totals. Appends a small audit summary.
    Also accumulates per-subtopic PERFORMANCE (a separate signal from the memory
    gate) that can satisfy prerequisites in the guided DAG.

    ``scope`` (``all`` | ``unit`` | ``subtopic``) and ``source`` (``official`` |
    ``generated``) set this test's representativeness weight (``readiness_weight``),
    which is accumulated as float ``weighted_questions`` / ``weighted_correct``
    ALONGSIDE the raw integer counts. The readiness band uses the weighted
    proportion; the give-up gate still uses the raw ``questions`` count."""
    raw = col.get_config(PRACTICE_STATS_KEY, None) or {}
    w = readiness_weight(scope, source)
    stats = {
        "questions": int(raw.get("questions", 0)) + result.questions,
        "correct": int(raw.get("correct", 0)) + result.correct,
        "tests": int(raw.get("tests", 0)) + 1,
        "weighted_questions": round(
            float(raw.get("weighted_questions", 0.0)) + w * result.questions, 6
        ),
        "weighted_correct": round(
            float(raw.get("weighted_correct", 0.0)) + w * result.correct, 6
        ),
    }
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
            "scope": scope,
            "source": source,
            "weight": round(w, 4),
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
