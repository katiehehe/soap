# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Calibration metrics for the score models (memory now, performance next).

A probabilistic model is *calibrated* when, among the times it predicts
probability ~p, about a fraction p actually happen. These pure, deterministic
functions measure that so anyone can re-run and get the same numbers:

- ``brier_score`` and ``log_loss`` are proper scoring rules (lower is better).
- ``reliability_bins`` / ``expected_calibration_error`` give the reliability curve
  and a single-number summary of how far predictions sit from outcomes.

The honesty/give-up rule applies to calibration too: below ``min_samples`` graded
predictions, ``calibration_report`` returns an explicit ``insufficient_data``
status instead of a shaky number. Nothing here fabricates a score; it only
scores predictions against real outcomes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# Below this many graded predictions we refuse to report a calibration number:
# a reliability curve over a handful of points is noise, not evidence.
DEFAULT_MIN_SAMPLES = 100


def _validate(preds: list[float], outcomes: list[int]) -> None:
    if len(preds) != len(outcomes):
        raise ValueError("preds and outcomes must have equal length")
    for p in preds:
        if not 0.0 <= p <= 1.0:
            raise ValueError(f"prediction out of [0, 1]: {p}")
    for o in outcomes:
        if o not in (0, 1):
            raise ValueError(f"outcome must be 0 or 1, got: {o}")


def brier_score(preds: list[float], outcomes: list[int]) -> float:
    """Mean squared error between predicted probability and outcome (0..1)."""
    _validate(preds, outcomes)
    if not preds:
        raise ValueError("need at least one sample")
    return sum((p - o) ** 2 for p, o in zip(preds, outcomes)) / len(preds)


def log_loss(preds: list[float], outcomes: list[int], eps: float = 1e-15) -> float:
    """Mean negative log-likelihood (a.k.a. cross-entropy); lower is better."""
    _validate(preds, outcomes)
    if not preds:
        raise ValueError("need at least one sample")
    total = 0.0
    for p, o in zip(preds, outcomes):
        p = min(1.0 - eps, max(eps, p))
        total += -(o * math.log(p) + (1 - o) * math.log(1.0 - p))
    return total / len(preds)


@dataclass(frozen=True)
class ReliabilityBin:
    lo: float
    hi: float
    count: int
    mean_pred: float
    mean_outcome: float


def reliability_bins(
    preds: list[float], outcomes: list[int], n_bins: int = 10
) -> list[ReliabilityBin]:
    """Group predictions into ``n_bins`` equal-width buckets and, for each,
    report the mean predicted probability vs the actual fraction that occurred.
    A perfectly calibrated model has ``mean_pred == mean_outcome`` in every bin."""
    _validate(preds, outcomes)
    if n_bins < 1:
        raise ValueError("n_bins must be >= 1")
    bins: list[ReliabilityBin] = []
    for b in range(n_bins):
        lo = b / n_bins
        hi = (b + 1) / n_bins
        # Last bin is closed on the right so p == 1.0 is included.
        idx = [
            i
            for i, p in enumerate(preds)
            if p >= lo and (p < hi or (b == n_bins - 1 and p <= hi))
        ]
        if not idx:
            bins.append(ReliabilityBin(lo, hi, 0, 0.0, 0.0))
            continue
        mean_pred = sum(preds[i] for i in idx) / len(idx)
        mean_outcome = sum(outcomes[i] for i in idx) / len(idx)
        bins.append(ReliabilityBin(lo, hi, len(idx), mean_pred, mean_outcome))
    return bins


def expected_calibration_error(
    preds: list[float], outcomes: list[int], n_bins: int = 10
) -> float:
    """Sample-weighted average gap between predicted and observed probability
    across the reliability bins. 0 = perfectly calibrated."""
    _validate(preds, outcomes)
    if not preds:
        raise ValueError("need at least one sample")
    n = len(preds)
    return sum(
        b.count / n * abs(b.mean_pred - b.mean_outcome)
        for b in reliability_bins(preds, outcomes, n_bins)
        if b.count
    )


@dataclass(frozen=True)
class CalibrationReport:
    status: str  # "ok" or "insufficient_data"
    n: int
    min_samples: int
    brier: float | None = None
    log_loss: float | None = None
    ece: float | None = None
    base_rate: float | None = None
    bins: list[ReliabilityBin] = field(default_factory=list)


def calibration_report(
    preds: list[float],
    outcomes: list[int],
    min_samples: int = DEFAULT_MIN_SAMPLES,
    n_bins: int = 10,
) -> CalibrationReport:
    """Full calibration report, or an honest ``insufficient_data`` result when
    there are fewer than ``min_samples`` graded predictions."""
    _validate(preds, outcomes)
    n = len(preds)
    if n < min_samples:
        return CalibrationReport(
            status="insufficient_data", n=n, min_samples=min_samples
        )
    return CalibrationReport(
        status="ok",
        n=n,
        min_samples=min_samples,
        brier=brier_score(preds, outcomes),
        log_loss=log_loss(preds, outcomes),
        ece=expected_calibration_error(preds, outcomes, n_bins),
        base_rate=sum(outcomes) / n,
        bins=reliability_bins(preds, outcomes, n_bins),
    )
