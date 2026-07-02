# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Reproducible held-out split + leakage scan (challenges 7e and the seeded
train/test split).

- ``train_test_split`` is deterministic given a seed, so anyone can re-run and
  get the same split.
- ``find_leaks`` flags any test item that also appears in training, either
  verbatim (after normalisation) or as a near-copy (high token overlap). A wrong
  or leaked test item would silently inflate scores, so this is wired as a gate.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

_WORD = re.compile(r"[a-z0-9]+")


def normalize(text: str) -> str:
    """Lowercase and collapse to word tokens joined by single spaces."""
    return " ".join(_WORD.findall(text.lower()))


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def jaccard(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def train_test_split(
    item_ids: list[str], test_frac: float = 0.2, seed: int = 0
) -> tuple[list[str], list[str]]:
    """Deterministic train/test split. Same ids + seed -> same split every run."""
    if not 0.0 <= test_frac <= 1.0:
        raise ValueError("test_frac must be in [0, 1]")
    ordered = sorted(set(item_ids))
    rng = random.Random(seed)
    shuffled = ordered[:]
    rng.shuffle(shuffled)
    n_test = round(len(shuffled) * test_frac)
    test = set(shuffled[:n_test])
    train_ids = [i for i in ordered if i not in test]
    test_ids = [i for i in ordered if i in test]
    return train_ids, test_ids


@dataclass(frozen=True)
class Leak:
    test_id: str
    train_id: str
    similarity: float


def find_leaks(
    train_items: list[tuple[str, str]],
    test_items: list[tuple[str, str]],
    threshold: float = 0.9,
) -> list[Leak]:
    """Return test items that appear in training (verbatim or near-copy).

    ``*_items`` are (id, text) pairs. A leak is an exact normalised match or a
    token-overlap (Jaccard) at or above ``threshold``.
    """
    train_norm: dict[str, str] = {}
    for tid, text in train_items:
        train_norm.setdefault(normalize(text), tid)

    leaks: list[Leak] = []
    for test_id, test_text in test_items:
        norm = normalize(test_text)
        if norm in train_norm:
            leaks.append(Leak(test_id, train_norm[norm], 1.0))
            continue
        best: Leak | None = None
        for train_id, train_text in train_items:
            sim = jaccard(test_text, train_text)
            if sim >= threshold and (best is None or sim > best.similarity):
                best = Leak(test_id, train_id, sim)
        if best is not None:
            leaks.append(best)
    return leaks
