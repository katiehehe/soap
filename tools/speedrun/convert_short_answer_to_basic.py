#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Convert already-seeded typed "SOA Short Answer" cards into Basic flip cards.

    python tools/speedrun/convert_short_answer_to_basic.py                 # default profile
    python tools/speedrun/convert_short_answer_to_basic.py --path /path/collection.anki2
    python tools/speedrun/convert_short_answer_to_basic.py --dry-run

Why this exists
---------------
Every seeded study-deck card is now a stock **Basic** front/back flashcard the
student self-grades (Again/Hard/Good/Easy). Computational cards used to be typed
``{{type:Answer}}`` "SOA Short Answer" cards, which didn't do the worked answers
justice. Fresh collections already build Basic cards; but the deck is seeded once
per collection (guarded), so a collection seeded before this change still holds
the old typed cards.

This one-off, idempotent maintenance step rewrites those in place:

  * Front stays the question; Back becomes the concise answer + the worked
    solution (MathJax preserved), so it looks exactly like a freshly seeded card.
  * SCOPED to seeded curriculum cards (matched by the ``difficulty::`` tag). The
    AI-generated *quarantine* cards share the notetype but never carry a
    ``difficulty::`` tag, so they are left exactly as-is.
  * Runs through Anki's own note-type conversion (``models.change``), mapping the
    single card template 1:1, so every card KEEPS its FSRS scheduling / review
    history and undo still works, so the collection is never corrupted.

Changing a note's notetype is a schema modification (it forces one full sync on
next sync, which pushes the fix to the phone too). Because it is schema-modifying
and one-time, it is a deliberate maintenance step: run with Anki CLOSED (it
holds an exclusive lock and caches config/notes in memory), not silently on load.
"""

from __future__ import annotations

import argparse
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _p in (os.path.join(_REPO, "pylib"), os.path.join(_REPO, "out", "pylib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import anki.collection  # noqa: E402,F401  (preload to avoid a circular import)
from anki.collection import Collection  # noqa: E402
from anki.speedrun.seed import (  # noqa: E402
    SHORT_ANSWER_NOTETYPE,
    convert_seeded_short_answer_to_basic,
)


def _default_collection_path() -> str:
    """Best-effort path to the desktop profile's collection (macOS/Linux/Windows)."""
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support/Anki2")
    elif os.name == "nt":
        base = os.path.join(os.environ.get("APPDATA", ""), "Anki2")
    else:
        base = os.path.expanduser("~/.local/share/Anki2")
    return os.path.join(base, "User 1", "collection.anki2")


def _seeded_short_answer_count(col: Collection) -> int:
    if col.models.by_name(SHORT_ANSWER_NOTETYPE) is None:
        return 0
    return len(col.find_notes(f'note:"{SHORT_ANSWER_NOTETYPE}" tag:difficulty::*'))


def convert(path: str, *, dry_run: bool) -> int:
    if not os.path.exists(path):
        print(f"collection not found: {path}", file=sys.stderr)
        return 2
    try:
        col = Collection(path)
    except Exception as exc:  # pragma: no cover - lock/other IO errors
        print(
            f"could not open collection (is Anki still running?): {exc}",
            file=sys.stderr,
        )
        return 2
    try:
        pending = _seeded_short_answer_count(col)
        if pending == 0:
            print("no seeded 'SOA Short Answer' cards found, nothing to do.")
            return 0
        print(f"found {pending} seeded typed short-answer card(s) to convert.")
        if dry_run:
            print("dry run: not modifying the collection.")
            return 0
        converted = convert_seeded_short_answer_to_basic(col)
        print(
            f"converted {converted} card(s) to Basic flip cards "
            "(FSRS history preserved). Sync to push the fix to the phone too."
        )
        return 0
    finally:
        col.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--path",
        default=_default_collection_path(),
        help="path to collection.anki2 (default: desktop 'User 1' profile)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="report how many cards would convert, without modifying the collection",
    )
    args = ap.parse_args()
    return convert(args.path, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
