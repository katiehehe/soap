#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Crash-recovery test (challenge 7g).

Repeatedly launches a worker that reviews/writes the collection, SIGKILLs it
mid-write, then reopens the collection and asserts zero corruption (SQLite
`pragma integrity_check` == "ok" and the collection is readable). Relies on the
Rust engine's transactional writes for durability.

Usage:
    out/pyenv/bin/python tools/speedrun/crash_test.py [--iterations 20]

Or via `make crash-test`.
"""

from __future__ import annotations

import argparse
import os
import random
import subprocess
import sys
import tempfile
import time

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PYLIBS = [os.path.join(_REPO, "pylib"), os.path.join(_REPO, "out", "pylib")]
for _p in _PYLIBS:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from anki.collection import Collection  # noqa: E402
from anki.speedrun.seed import ROOT_DECK, build_deck  # noqa: E402


def run_worker(path: str) -> None:
    """Continuously write to the collection until killed."""
    col = Collection(path)
    col.decks.select(col.decks.id(ROOT_DECK))
    notetype = col.models.by_name("Basic")
    assert notetype is not None
    extra_deck = col.decks.id(f"{ROOT_DECK}::general::extra")
    counter = 0
    while True:
        card = col.sched.getCard()
        if card is not None:
            col.sched.answerCard(card, 3)
        else:
            note = col.new_note(notetype)
            note["Front"] = f"crash-{counter}"
            note["Back"] = "x"
            note.add_tag("subtopic::general::conditional")
            col.add_note(note, extra_deck)
            counter += 1


def main() -> None:
    # The worker subprocess is spawned with `--worker <path>`; handle it before
    # argparse so the child actually enters the write loop (otherwise it would
    # exit on an unrecognized-argument error before writing anything).
    if "--worker" in sys.argv:
        run_worker(sys.argv[sys.argv.index("--worker") + 1])
        return

    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=20)
    args = parser.parse_args()

    path = tempfile.mktemp(suffix=".anki2")
    col = Collection(path)
    build_deck(col)
    col.close(downgrade=False)

    env = {**os.environ, "PYTHONPATH": os.pathsep.join(_PYLIBS)}
    for i in range(args.iterations):
        proc = subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "--worker", path],
            env=env,
        )
        # Let it get into the write loop, then kill it mid-flight.
        time.sleep(random.uniform(0.2, 0.7))
        proc.kill()
        proc.wait()

        # Reopen and verify integrity after every crash.
        col = Collection(path)
        integrity = col.db.scalar("pragma integrity_check")
        card_count = col.card_count()
        col.close()
        if integrity != "ok":
            print(f"CORRUPTION after crash {i + 1}: {integrity}")
            sys.exit(1)
        print(f"crash {i + 1}/{args.iterations}: integrity ok, cards={card_count}")

    print(f"\nOK: survived {args.iterations} mid-review SIGKILLs with zero corruption")


if __name__ == "__main__":
    main()
