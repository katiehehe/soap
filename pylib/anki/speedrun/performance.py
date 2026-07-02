# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Performance model (score-model Step 2): P(correct) on a NEW exam-style question.

Per the brief (section 4 and section 9 Step 2), performance is NOT memory: it
predicts whether the student gets a *new, disguised* exam-style question right,
from topic mastery, question difficulty, response time, and syllabus coverage.

This is a small, self-contained, DETERMINISTIC logistic-regression pipeline (no
external ML dependencies) with:

- a seeded train / held-out split (via ``evalsplit.train_test_split``),
- calibration via ``calibration.py`` (Brier / log loss / ECE / reliability),
- a majority-class baseline to beat,
- an explicit insufficient-data give-up (no metric below a minimum test size).

Honesty: this NEVER fabricates a student result. On the real deck there is not
yet a labelled held-out set of disguised questions, so the app shows "not yet
measured". The pipeline is validated on a clearly-labelled SYNTHETIC fixture
(``tools/speedrun/evals/performance_eval.py``) so the code path is real,
reproducible, and leakage-checked, ready to run the moment real data exists.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from anki.speedrun.calibration import CalibrationReport, calibration_report

# Feature order for the model's weight vector (index 0 is the bias term).
FEATURE_NAMES = ("bias", "mastery", "difficulty", "response_time", "coverage")


@dataclass(frozen=True)
class PerformanceExample:
    """One graded, disguised exam-style question for a student.

    All features are normalised to [0, 1]. ``correct`` is the 0/1 outcome;
    ``text`` is kept for the leakage scan (held-out items must not leak into
    training).
    """

    id: str
    mastery: float
    difficulty: float
    response_time: float
    coverage: float
    correct: int
    text: str = ""


def _features(ex: PerformanceExample) -> list[float]:
    return [1.0, ex.mastery, ex.difficulty, ex.response_time, ex.coverage]


def _sigmoid(z: float) -> float:
    # Numerically stable logistic.
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


@dataclass
class LogisticModel:
    weights: list[float]

    def predict_proba(self, ex: PerformanceExample) -> float:
        z = sum(w * x for w, x in zip(self.weights, _features(ex)))
        return _sigmoid(z)


def train_logistic(
    train: list[PerformanceExample],
    *,
    seed: int = 0,
    epochs: int = 400,
    lr: float = 0.3,
    l2: float = 1e-4,
) -> LogisticModel:
    """Deterministic logistic regression via seeded SGD with L2 on the non-bias
    weights. Same examples + seed -> identical weights every run."""
    rng = random.Random(seed)
    n_features = len(FEATURE_NAMES)
    w = [0.0] * n_features
    order = list(range(len(train)))
    for _ in range(epochs):
        rng.shuffle(order)
        for i in order:
            ex = train[i]
            x = _features(ex)
            p = _sigmoid(sum(wj * xj for wj, xj in zip(w, x)))
            err = p - ex.correct
            for j in range(n_features):
                grad = err * x[j] + (l2 * w[j] if j > 0 else 0.0)
                w[j] -= lr * grad
    return LogisticModel(w)


def _auc(preds: list[float], labels: list[int]) -> float:
    """Rank-based ROC AUC (probability a random positive outranks a random
    negative). 0.5 = no better than chance."""
    pos = [p for p, y in zip(preds, labels) if y == 1]
    neg = [p for p, y in zip(preds, labels) if y == 0]
    if not pos or not neg:
        return 0.5
    wins = 0.0
    for p in pos:
        for n in neg:
            wins += 1.0 if p > n else (0.5 if p == n else 0.0)
    return wins / (len(pos) * len(neg))


@dataclass(frozen=True)
class PerformanceEval:
    status: str  # "ok" or "insufficient_data"
    n_train: int
    n_test: int
    accuracy: float | None = None
    auc: float | None = None
    baseline_accuracy: float | None = None
    beats_baseline: bool | None = None
    calibration: CalibrationReport | None = None


def evaluate(
    model: LogisticModel,
    test: list[PerformanceExample],
    *,
    n_train: int,
    min_test: int = 30,
    min_samples: int = 30,
) -> PerformanceEval:
    """Evaluate on the held-out set: accuracy, AUC, calibration, and whether it
    beats a majority-class baseline. Abstains (insufficient_data) below
    ``min_test`` so we never report a metric from a handful of points."""
    n = len(test)
    if n < min_test:
        return PerformanceEval(status="insufficient_data", n_train=n_train, n_test=n)
    preds = [model.predict_proba(ex) for ex in test]
    labels = [ex.correct for ex in test]
    accuracy = sum(1 for p, y in zip(preds, labels) if (p >= 0.5) == (y == 1)) / n
    base_rate = sum(labels) / n
    baseline_accuracy = max(base_rate, 1.0 - base_rate)  # majority class
    return PerformanceEval(
        status="ok",
        n_train=n_train,
        n_test=n,
        accuracy=accuracy,
        auc=_auc(preds, labels),
        baseline_accuracy=baseline_accuracy,
        beats_baseline=accuracy > baseline_accuracy,
        calibration=calibration_report(preds, labels, min_samples=min_samples),
    )


def train_test_split_examples(
    examples: list[PerformanceExample],
    *,
    seed: int = 0,
    test_frac: float = 0.3,
) -> tuple[list[PerformanceExample], list[PerformanceExample]]:
    """Deterministic held-out split of examples by id (reuses the seeded
    splitter). Same examples + seed -> same split."""
    from anki.speedrun.evalsplit import train_test_split

    by_id = {ex.id: ex for ex in examples}
    train_ids, test_ids = train_test_split(list(by_id), test_frac=test_frac, seed=seed)
    return [by_id[i] for i in train_ids], [by_id[i] for i in test_ids]


def run_pipeline(
    examples: list[PerformanceExample],
    *,
    seed: int = 0,
    test_frac: float = 0.3,
    min_test: int = 30,
    min_samples: int = 30,
) -> PerformanceEval:
    """End-to-end: seeded split -> train -> held-out evaluation. Deterministic."""
    train, test = train_test_split_examples(examples, seed=seed, test_frac=test_frac)
    model = train_logistic(train, seed=seed)
    return evaluate(
        model, test, n_train=len(train), min_test=min_test, min_samples=min_samples
    )
