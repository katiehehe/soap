# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from anki.speedrun.evalsplit import find_leaks, train_test_split


def test_split_is_reproducible_and_disjoint():
    ids = [f"q{i}" for i in range(20)]
    a = train_test_split(ids, test_frac=0.25, seed=42)
    b = train_test_split(ids, test_frac=0.25, seed=42)
    assert a == b  # same seed -> identical split, anyone can re-run

    train, test = a
    assert set(train).isdisjoint(test)
    assert sorted(train + test) == sorted(ids)
    assert len(test) == 5

    # A different seed produces a different split.
    assert train_test_split(ids, test_frac=0.25, seed=7) != a


def test_leakage_detects_exact_and_near_copies_and_passes_clean():
    train = [
        ("t1", "P(A|B) = P(A and B) / P(B)"),
        ("t2", "binomial mean is np"),
    ]
    # Exact leak (identical after normalisation).
    assert find_leaks(train, [("x1", "p(a|b) = p(a AND b)/p(b)")])
    # Near-copy leak (high token overlap).
    assert find_leaks(train, [("x2", "the binomial mean is np")], threshold=0.7)
    # Clean: an unrelated test item is not flagged.
    assert (
        find_leaks(train, [("x3", "exponential variance is 1 / lambda squared")]) == []
    )
