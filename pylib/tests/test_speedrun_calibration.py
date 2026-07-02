# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import math

import pytest

from anki.speedrun.calibration import (
    brier_score,
    calibration_report,
    expected_calibration_error,
    log_loss,
    reliability_bins,
)


def test_brier_score_known_values():
    # Perfect predictions -> 0.
    assert brier_score([1.0, 0.0, 1.0, 0.0], [1, 0, 1, 0]) == 0.0
    # Always 0.5 on a balanced set -> 0.25.
    assert brier_score([0.5, 0.5, 0.5, 0.5], [1, 1, 0, 0]) == pytest.approx(0.25)


def test_log_loss_known_values():
    # Always 0.5 -> -ln(0.5) = ln 2.
    assert log_loss([0.5, 0.5], [1, 0]) == pytest.approx(math.log(2))
    # Near-perfect predictions -> ~0.
    assert log_loss([1.0, 0.0], [1, 0]) < 1e-6


def test_reliability_bins_place_predictions_correctly():
    bins = reliability_bins([0.05, 0.15, 0.95], [0, 0, 1], n_bins=10)
    assert bins[0].count == 1 and bins[0].mean_pred == pytest.approx(0.05)
    assert bins[1].count == 1 and bins[1].mean_pred == pytest.approx(0.15)
    assert bins[9].count == 1 and bins[9].mean_outcome == 1.0
    # p == 1.0 lands in the last (closed) bin, not dropped.
    assert reliability_bins([1.0], [1], n_bins=10)[9].count == 1


def test_expected_calibration_error_zero_when_calibrated():
    # Each bin's mean prediction equals its outcome fraction -> ECE 0.
    assert expected_calibration_error([0.0, 0.0, 1.0, 1.0], [0, 0, 1, 1]) == 0.0
    # A confidently-wrong model has a large ECE.
    assert expected_calibration_error([1.0, 1.0], [0, 0]) == pytest.approx(1.0)


def test_calibration_report_gives_up_below_min_samples():
    # The honesty rule for calibration: too few points -> no number.
    report = calibration_report([0.5] * 4, [1, 0, 1, 0], min_samples=5)
    assert report.status == "insufficient_data"
    assert report.n == 4
    assert report.brier is None and report.log_loss is None


def test_calibration_report_reports_metrics_above_threshold():
    preds = [0.5] * 10
    outcomes = [1, 0, 1, 0, 1, 0, 1, 0, 1, 0]
    report = calibration_report(preds, outcomes, min_samples=5)
    assert report.status == "ok"
    assert report.n == 10
    assert report.brier == pytest.approx(0.25)
    assert report.log_loss == pytest.approx(math.log(2))
    assert report.base_rate == pytest.approx(0.5)


def test_calibration_is_deterministic():
    preds = [i / 20 for i in range(20)]
    outcomes = [i % 2 for i in range(20)]
    a = calibration_report(preds, outcomes, min_samples=5)
    b = calibration_report(preds, outcomes, min_samples=5)
    assert a == b


def test_validation_rejects_bad_input():
    with pytest.raises(ValueError):
        brier_score([0.5], [1, 0])  # length mismatch
    with pytest.raises(ValueError):
        brier_score([1.5], [1])  # prob out of range
    with pytest.raises(ValueError):
        brier_score([0.5], [2])  # outcome not 0/1
