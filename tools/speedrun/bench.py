#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""One-command benchmark (challenge 7h).

Loads a large tagged Exam P deck and reports p50 / p95 / worst for the actions
that must stay fast on a big collection: building the review queue (next card),
the mastery query, mastery-ordered new cards, and the readiness computation.

Usage:
    out/pyenv/bin/python tools/speedrun/bench.py [--cards 50000] [--reps 200]

Or via `make bench` (defaults to 50k cards).
"""

from __future__ import annotations

import argparse
import os
import sys
import time

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _p in (os.path.join(_REPO, "pylib"), os.path.join(_REPO, "out", "pylib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from anki.collection import Collection  # noqa: E402
from anki.speedrun import (  # noqa: E402
    difficulty_tag,
    expected_subtopic_tags,
    load_topics,
    subtopic_tag,
    unit_tag,
    unit_weights,
)


def generate_deck(col: Collection, n_cards: int) -> None:
    topics = load_topics()
    subs = [(u["id"], s["id"]) for u in topics["units"] for s in u["subtopics"]]
    notetype = col.models.by_name("Basic")
    assert notetype is not None
    difficulties = ["easy", "medium", "hard"]
    deck_id = col.decks.id("SOA Exam P::bench")
    assert deck_id is not None
    col.decks.select(deck_id)
    for i in range(n_cards):
        unit_id, sub_id = subs[i % len(subs)]
        note = col.new_note(notetype)
        note["Front"] = f"Q{i} for {sub_id}"
        note["Back"] = f"A{i}"
        note.add_tag(unit_tag(unit_id))
        note.add_tag(subtopic_tag(unit_id, sub_id))
        note.add_tag(difficulty_tag(difficulties[i % 3]))
        col.add_note(note, deck_id)


def report(name: str, samples_ms: list[float]) -> None:
    s = sorted(samples_ms)

    def pct(p: float) -> float:
        return s[min(len(s) - 1, int(p / 100.0 * len(s)))]

    print(
        f"{name:<28} p50={pct(50):8.2f}ms  p95={pct(95):8.2f}ms  "
        f"worst={s[-1]:8.2f}ms  (n={len(s)})"
    )


def bench_action(fn, reps: int) -> list[float]:
    out = []
    for _ in range(reps):
        start = time.perf_counter()
        fn()
        out.append((time.perf_counter() - start) * 1000.0)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cards", type=int, default=50000)
    parser.add_argument("--reps", type=int, default=200)
    args = parser.parse_args()

    path = "/tmp/speedrun-bench.anki2"
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(path + suffix)
        except FileNotFoundError:
            pass
    col = Collection(path)

    print(f"Generating {args.cards} cards ...", flush=True)
    t0 = time.perf_counter()
    generate_deck(col, args.cards)
    print(f"  generated in {time.perf_counter() - t0:.1f}s\n")

    expected = expected_subtopic_tags()
    from anki import speedrun_pb2

    weight_msgs = [
        speedrun_pb2.UnitWeight(unit_id=uid, weight=w) for uid, w in unit_weights()
    ]

    print(f"Timing actions on a {args.cards}-card collection:\n")
    report(
        "build queue (next card)",
        bench_action(lambda: col.sched.getCard(), args.reps),
    )
    report(
        "mastery query",
        bench_action(
            lambda: col._backend.get_mastery_state(expected_subtopics=expected),
            args.reps,
        ),
    )
    report(
        "mastery-ordered new cards",
        bench_action(
            lambda: col._backend.get_mastery_ordered_new_cards(
                expected_subtopics=expected
            ),
            args.reps,
        ),
    )
    report(
        "readiness (give-up rule)",
        bench_action(
            lambda: col._backend.compute_readiness(
                expected_subtopics=expected, units=weight_msgs
            ),
            args.reps,
        ),
    )
    col.close()


if __name__ == "__main__":
    main()
