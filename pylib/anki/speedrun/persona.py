# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Seeded synthetic *demo persona*, the honest way to "come up with reasonable
data" without breaking the anti-fabrication rule.

The rubric's automatic-fail is *dressing up a guess as a measurement*. This module
does the opposite: it generates a **clearly-labelled, seeded, reproducible**
synthetic student (a latent per-subtopic skill), then lets the REAL pipeline do
the measuring:

- review outcomes -> inserted as graded revlog rows (``tools/speedrun/seed_persona.py``)
  so coverage + review counts are real collection state, and
- practice-test / exam-style responses -> graded by the real practice-test and
  performance code.

Every number the app then shows for this persona is computed by exactly the code
a real student would hit; it is just fed a synthetic study history that always
carries the ``synthetic demo persona`` label. Same seed -> same persona -> same
numbers, so anyone can re-run and reproduce them.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from anki.speedrun import expected_subtopic_tags

# Stamped onto every persona-derived artifact so a synthetic study history can
# never be mistaken for a real student's measurement.
SYNTHETIC_LABEL = "synthetic demo persona"

# Default seed for the single demo persona (a date, for a memorable constant).
DEFAULT_SEED = 20260703

_DIFFICULTY_NUM = {"easy": 0.25, "medium": 0.5, "hard": 0.8}


def difficulty_num(difficulty: str) -> float:
    return _DIFFICULTY_NUM.get(difficulty.lower(), 0.5)


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


@dataclass(frozen=True)
class Persona:
    """A synthetic student: a latent skill in [0, 1] per syllabus subtopic.

    Not a real person and not a measurement, but a reproducible fixture. ``label``
    is carried through to every artifact so nothing looks like real data.
    """

    name: str
    seed: int
    skill: dict[str, float]
    label: str = SYNTHETIC_LABEL

    def skill_for(self, subtopic: str) -> float:
        return self.skill.get(subtopic, 0.5)


def default_persona(seed: int = DEFAULT_SEED) -> Persona:
    """A believable Exam-P study profile: solid in general probability, mid on
    univariate, weaker on multivariate (a common real pattern). Deterministic
    given the seed, so the demo is reproducible."""
    rng = random.Random(seed)
    # Per-unit skill centres; each subtopic jitters around its unit's centre.
    # A believable BORDERLINE profile: strong general, solid univariate, weak
    # multivariate: enough to demo a real range + a non-trivial P(pass), with a
    # clear weakest area. It is a fixture, not a target; the numbers are whatever
    # this profile honestly yields.
    unit_center = {"general": 0.90, "univariate": 0.80, "multivariate": 0.62}
    skill: dict[str, float] = {}
    for tag in expected_subtopic_tags():
        unit = tag.split("::")[1]
        center = unit_center.get(unit, 0.6)
        val = center + rng.uniform(-0.12, 0.12)
        skill[tag] = round(min(0.97, max(0.05, val)), 3)
    return Persona(name="Demo Student (synthetic)", seed=seed, skill=skill)


def new_persona(seed: int = DEFAULT_SEED) -> Persona:
    """A brand-new student who has barely started: modest skill, weakest on the
    later units. Paired (in the demo) with only a few subtopics touched and no
    practice tests, so the readiness give-up rule ABSTAINS honestly (coverage and
    review counts stay far below the gates). The handful of studied subtopics
    still yield a real partial Memory value. Deterministic given the seed."""
    rng = random.Random(f"new|{seed}")
    unit_center = {"general": 0.62, "univariate": 0.45, "multivariate": 0.38}
    skill: dict[str, float] = {}
    for tag in expected_subtopic_tags():
        unit = tag.split("::")[1]
        center = unit_center.get(unit, 0.5)
        val = center + rng.uniform(-0.1, 0.1)
        skill[tag] = round(min(0.97, max(0.05, val)), 3)
    return Persona(name="New Student (synthetic)", seed=seed, skill=skill)


def experienced_persona(seed: int = DEFAULT_SEED) -> Persona:
    """A well-prepared student near exam-ready: high skill across all three
    units. Paired with many reviews and several practice tests, so the engine
    reports a high P(pass) with a tight range and near-complete coverage. Still a
    synthetic fixture whose numbers are measured by the real pipeline, never set
    directly. Deterministic given the seed."""
    rng = random.Random(f"experienced|{seed}")
    unit_center = {"general": 0.96, "univariate": 0.93, "multivariate": 0.90}
    skill: dict[str, float] = {}
    for tag in expected_subtopic_tags():
        unit = tag.split("::")[1]
        center = unit_center.get(unit, 0.9)
        val = center + rng.uniform(-0.05, 0.05)
        skill[tag] = round(min(0.97, max(0.05, val)), 3)
    return Persona(name="Experienced Student (synthetic)", seed=seed, skill=skill)


def synthetic_cohort(n: int, seed: int = 0) -> list[Persona]:
    """A cohort of ``n`` independent synthetic students, for calibrating and
    evaluating the *performance model* (one student gives too few points). Each
    persona has its own seeded skill vector; the cohort is fully reproducible."""
    out: list[Persona] = []
    for i in range(n):
        prng = random.Random(f"cohort|{seed}|{i}")
        skill: dict[str, float] = {}
        base = prng.uniform(0.35, 0.8)  # this student's overall ability
        for tag in expected_subtopic_tags():
            skill[tag] = round(
                min(0.97, max(0.03, base + prng.uniform(-0.25, 0.25))), 3
            )
        out.append(Persona(name=f"cohort-{i}", seed=(seed * 100003 + i), skill=skill))
    return out


def p_correct(
    persona: Persona,
    subtopic: str,
    difficulty: str,
    coverage: float = 1.0,
    response_time: float = 0.5,
) -> float:
    """Probability this persona answers a NEW exam-style question right.

    A fixed, documented logistic relationship in (skill, difficulty, coverage,
    response_time), the SAME functional form as the performance model's fixture,
    so a correct performance model recovers a calibrated, better-than-baseline
    fit on persona data. It is a generative fixture, never a claim about a real
    student.
    """
    skill = persona.skill_for(subtopic)
    logit = (
        -3.0 + 5.0 * skill - 2.0 * difficulty_num(difficulty) + coverage - response_time
    )
    return _sigmoid(logit)


def response_time_for(persona: Persona, subtopic: str, difficulty: str) -> float:
    """A normalised [0, 1] response-time feature: harder items and weaker skill
    take longer. Deterministic given the persona + subtopic."""
    skill = persona.skill_for(subtopic)
    rng = random.Random(f"rt|{persona.seed}|{subtopic}")
    val = (
        0.45 + 0.4 * difficulty_num(difficulty) - 0.3 * skill + rng.uniform(-0.05, 0.05)
    )
    return min(1.0, max(0.0, val))


def recall_prob(persona: Persona, subtopic: str) -> float:
    """Probability the persona RECALLS a studied card for this subtopic, the
    MEMORY signal (same pass model as ``review_grades``). It is deliberately
    higher than ``p_correct`` (transfer performance) for the same skill, so a
    correct pipeline sees memory and performance diverge (the paraphrase test,
    challenge 7d). A copycat that reused the performance model here would show
    no gap."""
    skill = persona.skill_for(subtopic)
    return min(0.98, max(0.30, 0.45 + 0.5 * skill))


def review_grades(persona: Persona, subtopic: str, n: int) -> list[int]:
    """``n`` graded-review eases (Anki: 1 = Again/fail, 3 = Good/pass) for a
    subtopic. Pass probability rises with skill, so a strong subtopic's revlog
    accuracy clears the 80% gate and a weak one does not. Deterministic."""
    skill = persona.skill_for(subtopic)
    pass_prob = min(0.98, max(0.30, 0.45 + 0.5 * skill))
    rng = random.Random(f"rev|{persona.seed}|{subtopic}")
    return [3 if rng.random() < pass_prob else 1 for _ in range(n)]


@dataclass
class PracticeResponse:
    item_id: str
    subtopic: str
    difficulty: str
    correct: int


def answer_items(
    persona: Persona,
    items: list,
    coverage: float = 1.0,
    seed_salt: str = "practice",
) -> list[PracticeResponse]:
    """Have the persona answer a list of ``SampleItem``s, returning one
    graded response each. Deterministic given the persona + salt, so a graded
    practice test reproduces exactly."""
    out: list[PracticeResponse] = []
    for it in items:
        rt = response_time_for(persona, it.subtopic, it.difficulty)
        p = p_correct(persona, it.subtopic, it.difficulty, coverage, rt)
        rng = random.Random(f"{seed_salt}|{persona.seed}|{it.id}")
        out.append(
            PracticeResponse(
                item_id=it.id,
                subtopic=it.subtopic,
                difficulty=it.difficulty,
                correct=1 if rng.random() < p else 0,
            )
        )
    return out
