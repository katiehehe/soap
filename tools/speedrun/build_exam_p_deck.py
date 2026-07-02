#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Build the tagged SOA Exam P deck for the review loop and the demo.

Usage (from a built checkout):

    out/pyenv/bin/python tools/speedrun/build_exam_p_deck.py [OUTPUT]

OUTPUT defaults to out/SOA-Exam-P.apkg.
  * ending in .apkg  -> writes an importable Anki package. Import it with
    File > Import in the desktop app (or share it to AnkiDroid). This is safe
    and non-destructive: it never touches your existing collection.
  * ending in .anki2 -> writes the deck straight into that collection file.

Every card is tagged with its unit, subtopic, and difficulty so the coverage
metric and the mastery-gated scheduler can reason about it.
"""

from __future__ import annotations

import os
import sys
import tempfile

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _p in (os.path.join(_REPO, "pylib"), os.path.join(_REPO, "out", "pylib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from anki.collection import Collection, ExportAnkiPackageOptions  # noqa: E402
from anki.speedrun.seed import build_deck  # noqa: E402


def _export_apkg(out_path: str) -> int:
    """Build the deck in a throwaway collection and export an importable .apkg."""
    with tempfile.TemporaryDirectory() as tmp:
        col = Collection(os.path.join(tmp, "build.anki2"))
        try:
            added = build_deck(col)
            col.export_anki_package(
                out_path=out_path,
                options=ExportAnkiPackageOptions(
                    with_scheduling=False,
                    with_deck_configs=False,
                    with_media=False,
                    legacy=True,
                ),
                limit=None,
            )
        finally:
            col.close()
    return added


def _build_collection(out_path: str) -> int:
    col = Collection(out_path)
    try:
        return build_deck(col)
    finally:
        col.close()


def main() -> None:
    default = os.path.join(_REPO, "out", "SOA-Exam-P.apkg")
    out_path = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else default)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    if out_path.endswith(".anki2"):
        added = _build_collection(out_path)
        print(f"Added {added} cards to collection {out_path}")
    else:
        added = _export_apkg(out_path)
        print(f"Built {added} cards across the SOA Exam P syllabus.")
        print(f"Importable deck written to: {out_path}")
        print("Import in Anki: File > Import > select this .apkg")


if __name__ == "__main__":
    main()
