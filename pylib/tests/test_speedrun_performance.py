# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from anki.speedrun.performance import (
    PerformanceExample,
    evaluate,
    run_pipeline,
    train_logistic,
    train_test_split_examples,
)


def _ex(i: int, mastery: float, correct: int) -> PerformanceExample:
    return PerformanceExample(
        id=f"q{i}",
        mastery=mastery,
        difficulty=0.5,
        response_time=0.5,
        coverage=0.5,
        correct=correct,
        text=f"question number {i}",
    )


def _separable(n: int = 120) -> list[PerformanceExample]:
    # Balanced, cleanly separable by mastery, kept away from the 0.5 boundary so
    # a correct model reaches ~100% held-out accuracy.
    out: list[PerformanceExample] = []
    for i in range(n):
        if i % 2 == 0:
            out.append(_ex(i, 0.15 + (i % 10) * 0.02, 0))  # low mastery -> wrong
        else:
            out.append(_ex(i, 0.75 + (i % 10) * 0.02, 1))  # high mastery -> right
    return out


def test_logistic_learns_separable_signal():
    model = train_logistic(_separable(120), seed=0)
    hi = PerformanceExample("hi", 0.9, 0.5, 0.5, 0.5, 1)
    lo = PerformanceExample("lo", 0.1, 0.5, 0.5, 0.5, 0)
    assert model.predict_proba(hi) > 0.5
    assert model.predict_proba(lo) < 0.5
    assert model.predict_proba(hi) > model.predict_proba(lo)


def test_predict_proba_in_range():
    model = train_logistic(_separable(60), seed=1)
    for m in (0.0, 0.3, 0.7, 1.0):
        p = model.predict_proba(PerformanceExample("x", m, 0.5, 0.5, 0.5, 0))
        assert 0.0 <= p <= 1.0


def test_training_is_deterministic():
    a = train_logistic(_separable(80), seed=7)
    b = train_logistic(_separable(80), seed=7)
    assert a.weights == b.weights


def test_pipeline_beats_baseline_and_calibrates_on_fixture():
    result = run_pipeline(
        _separable(200), seed=0, test_frac=0.3, min_test=10, min_samples=10
    )
    assert result.status == "ok"
    assert result.accuracy is not None and result.accuracy >= 0.9
    assert result.auc is not None and result.auc >= 0.9
    assert result.beats_baseline is True
    assert result.calibration is not None and result.calibration.status == "ok"


def test_evaluate_gives_up_below_min_test():
    # The honesty rule for the performance model: too small a held-out set -> no
    # metric, an explicit insufficient-data result.
    data = _separable(40)
    model = train_logistic(data, seed=0)
    result = evaluate(model, data[:5], n_train=35, min_test=30)
    assert result.status == "insufficient_data"
    assert result.accuracy is None


def test_split_is_deterministic_and_disjoint():
    data = _separable(50)
    tr1, te1 = train_test_split_examples(data, seed=3, test_frac=0.3)
    tr2, te2 = train_test_split_examples(data, seed=3, test_frac=0.3)
    train_ids1 = [e.id for e in tr1]
    assert train_ids1 == [e.id for e in tr2]
    assert [e.id for e in te1] == [e.id for e in te2]
    assert set(train_ids1).isdisjoint(e.id for e in te1)
    assert len(tr1) + len(te1) == len(data)
