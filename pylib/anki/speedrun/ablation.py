# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Study-feature ablation (rubric section 8): does the WITHIN-UNIT interleaving
tier of the three-tier scheduler help, at equal study time?

Three builds (see ``docs/study-feature-ablation.md`` for the pre-registration):

1. **Full**    — Blocked -> Within-unit interleave -> (Cross-unit). Confusable
   sub-types of a unit are interleaved *together*.
2. **Ablated** — Blocked -> ONE global mixed pool (the within-unit tier removed);
   cleared subtopics mix with everything, so sibling sub-types are diluted.
3. **Plain**   — stock deck order (blocked, no deliberate interleaving).

Honesty (this is the crux). There is no real cohort in a week, so this is a
SEEDED SIMULATION on the labelled synthetic persona cohort, and it is built so it
CANNOT smuggle in the conclusion:

- **Equal study time**: every build studies the exact same multiset of reps, so
  each subtopic's proficiency is identical across builds. Only the ORDER differs.
- The single mechanism by which order can matter is a **discrimination** boost on
  confusable within-unit questions, controlled by one explicit effect-size knob,
  ``disc_gain`` (in logits), grounded in the interleaving literature.
- At ``disc_gain = 0`` the three builds are provably identical (the null). Any
  separation only appears for an *assumed* positive effect size, and we report
  the whole sweep — including the null. The real effect size for real students is
  unknown and needs real study logs; this is a design + sensitivity analysis, not
  a measured claim about the feature.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from anki.speedrun import expected_subtopic_tags
from anki.speedrun.persona import Persona, difficulty_num

BUILDS = ("full", "ablated", "plain")

# Study budget per subtopic and how many of those reps are the initial blocked
# phase (shared by Full and Ablated). Total reps are identical across builds, so
# proficiency is held equal — only the order (interleaving) changes.
REPS_PER_SUBTOPIC = 8
BLOCK_REPS = 3


def _unit_of(tag: str) -> str:
    parts = tag.split("::")
    return parts[1] if len(parts) == 3 else ""


def subtopics_by_unit() -> dict[str, list[str]]:
    """Syllabus subtopics grouped by unit, in a fixed order (deterministic)."""
    by_unit: dict[str, list[str]] = {}
    for tag in expected_subtopic_tags():
        by_unit.setdefault(_unit_of(tag), []).append(tag)
    return by_unit


def _round_robin(remaining: dict[str, int]) -> list[str]:
    """Interleave the remaining reps of several subtopics by cycling through them,
    so consecutive items are different subtopics (deterministic)."""
    seq: list[str] = []
    keys = list(remaining.keys())
    left = dict(remaining)
    while any(v > 0 for v in left.values()):
        for k in keys:
            if left[k] > 0:
                seq.append(k)
                left[k] -= 1
    return seq


def build_sequence(build: str) -> list[str]:
    """The order in which subtopic reps are studied under a given build.

    All builds contain the SAME multiset (each subtopic ``REPS_PER_SUBTOPIC``
    times) — equal study time — so they differ only in ordering.
    """
    by_unit = subtopics_by_unit()
    all_subs = [s for subs in by_unit.values() for s in subs]

    if build == "plain":
        # Stock deck order: all reps of one subtopic, then the next (blocked).
        seq: list[str] = []
        for s in all_subs:
            seq.extend([s] * REPS_PER_SUBTOPIC)
        return seq

    # Full and Ablated share the initial blocked phase.
    seq = []
    for s in all_subs:
        seq.extend([s] * BLOCK_REPS)
    rest = REPS_PER_SUBTOPIC - BLOCK_REPS

    if build == "full":
        # Within-unit interleave: cycle a unit's own siblings together, unit by
        # unit — confusable sub-types are mixed *with each other*.
        for subs in by_unit.values():
            seq.extend(_round_robin({s: rest for s in subs}))
        return seq
    if build == "ablated":
        # One global mixed pool: cycle ALL subtopics across ALL units, so a
        # unit's siblings are separated by unrelated cross-unit items.
        seq.extend(_round_robin({s: rest for s in all_subs}))
        return seq
    raise ValueError(f"unknown build: {build}")


def within_unit_interleaving(seq: list[str]) -> float:
    """Fraction of adjacent pairs that are DIFFERENT subtopics of the SAME unit.

    This is the exposure that the within-unit tier is meant to create; it is the
    only quantity the builds differ on, and it drives the discrimination boost.
    """
    if len(seq) < 2:
        return 0.0
    hits = 0
    for a, b in zip(seq, seq[1:]):
        if a != b and _unit_of(a) == _unit_of(b):
            hits += 1
    return hits / (len(seq) - 1)


def rep_counts(seq: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for s in seq:
        counts[s] = counts.get(s, 0) + 1
    return counts


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


def p_correct_confusable(
    persona: Persona,
    subtopic: str,
    difficulty: str,
    interleave: float,
    disc_gain: float,
) -> float:
    """P(correct) on a confusable within-unit exam question.

    Ability (skill, difficulty) is identical across builds — equal study. The
    only build-dependent term is ``disc_gain * interleave``: the discrimination
    boost from having interleaved the confusable siblings. ``disc_gain = 0``
    removes it entirely, so all builds coincide (the null).
    """
    skill = persona.skill_for(subtopic)
    logit = -1.0 + 3.0 * skill - 1.5 * difficulty_num(difficulty) + disc_gain * interleave
    return _sigmoid(logit)


@dataclass(frozen=True)
class BuildResult:
    build: str
    interleave: float
    accuracy_mean: float
    accuracy_lo: float
    accuracy_hi: float


def evaluate_build(
    build: str,
    cohort: list[Persona],
    items: list,
    disc_gain: float,
) -> BuildResult:
    """Expected accuracy of the cohort on the held-out confusable questions under
    a build's interleaving exposure. Deterministic (expected probabilities, no
    sampling noise); the lo/hi span the per-student means (a reported range)."""
    interleave = within_unit_interleaving(build_sequence(build))
    per_student: list[float] = []
    for persona in cohort:
        ps = [
            p_correct_confusable(
                persona, it.subtopic, it.difficulty, interleave, disc_gain
            )
            for it in items
        ]
        per_student.append(sum(ps) / len(ps) if ps else 0.0)
    mean = sum(per_student) / len(per_student) if per_student else 0.0
    return BuildResult(
        build=build,
        interleave=round(interleave, 4),
        accuracy_mean=mean,
        accuracy_lo=min(per_student) if per_student else 0.0,
        accuracy_hi=max(per_student) if per_student else 0.0,
    )


def evaluate_all(
    cohort: list[Persona],
    items: list,
    disc_gain: float,
) -> dict[str, BuildResult]:
    return {b: evaluate_build(b, cohort, items, disc_gain) for b in BUILDS}
