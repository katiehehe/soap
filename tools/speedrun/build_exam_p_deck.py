#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Seed a small, tagged SOA Exam P deck into a collection for the review loop.

Usage (from a built checkout):

    out/pyenv/bin/python tools/speedrun/build_exam_p_deck.py [collection.anki2]

Defaults to /tmp/soap-examp.anki2. Open the resulting profile in the desktop app
to run a review session on the deck.
"""

from __future__ import annotations

import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _p in (os.path.join(_REPO, "pylib"), os.path.join(_REPO, "out", "pylib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from anki.collection import Collection  # noqa: E402
from anki.speedrun.seed import build_deck  # noqa: E402


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/soap-examp.anki2"
    col = Collection(path)
    try:
        added = build_deck(col)
        print(f"Added {added} cards across 3 units to {path}")
    finally:
        col.close()


if __name__ == "__main__":
    main()
