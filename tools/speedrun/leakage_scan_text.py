#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Source-vs-held-out leakage gate (challenge 7e, generation side).

Any material used as an AI GENERATION INPUT (source passages, a reference PDF, a
scraped note set) must NOT contain the held-out evaluation items, or scores are
inflated by memorisation — a rubric AUTOMATIC FAIL. This scans a source against
the held-out corpus and exits non-zero if any held-out item is reproduced in the
source (verbatim or near-copy), so it can gate CI / a source drop-in.

It complements ``leakage_scan.py`` (which splits ONE item set into train/test):
here the source is a long free-text blob (a PDF or note file), so we detect a
reproduced problem by word-shingle CONTAINMENT — the fraction of a held-out
item's k-word shingles that appear verbatim in the source — plus an exact
normalised-substring check. This is exactly the method that caught the ACTEX
manual reproducing the official SOA sample questions.

Usage:
    # Validate the committed generation sources (the CI gate):
    python tools/speedrun/leakage_scan_text.py --source pylib/anki/speedrun/gen_sources.json

    # Ad-hoc: vet a dropped-in reference before using it as a source:
    python tools/speedrun/leakage_scan_text.py --source "some manual.pdf"
    python tools/speedrun/leakage_scan_text.py --source notes.txt --threshold 0.4
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _p in (os.path.join(_REPO, "pylib"), os.path.join(_REPO, "out", "pylib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from anki.speedrun.evalsplit import normalize  # noqa: E402

_WORD = re.compile(r"[a-z0-9]+")
_SHINGLE_K = 8


def _tokens(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def _shingles(tokens: list[str], k: int = _SHINGLE_K) -> set[tuple[str, ...]]:
    if len(tokens) < k:
        return {tuple(tokens)} if tokens else set()
    return {tuple(tokens[i : i + k]) for i in range(len(tokens) - k + 1)}


def _held_out_items() -> list[tuple[str, str]]:
    """(id, question) for the held-out corpus: the real SOA set if the owner
    dropped it in, plus the committed original fallback."""
    from anki.speedrun.soa_sample import _FALLBACK_PATH, _REAL_DATA_PATH

    items: list[tuple[str, str]] = []
    for path, label in ((_REAL_DATA_PATH, "real"), (_FALLBACK_PATH, "fallback")):
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for it in data.get("items", []):
            items.append((f"{label}:{it['id']}", str(it["question"])))
    return items


def _source_text(path: str) -> str:
    """Extract the source's text: a PDF (pypdf), a gen_sources.json (its
    passages + names + key terms), or a raw text file."""
    lower = path.lower()
    if lower.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(path)
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    if lower.endswith(".json"):
        data = json.loads(open(path, encoding="utf-8").read())
        sources = data.get("sources", data if isinstance(data, list) else [])
        parts: list[str] = []
        for s in sources:
            parts += [
                str(s.get("name", "")),
                str(s.get("passage", "")),
                " ".join(s.get("key_terms", [])),
            ]
        return "\n".join(parts)
    return open(path, encoding="utf-8").read()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="PDF / .json sources / .txt")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="containment (fraction of an item's shingles in the source) that "
        "counts as leakage (default 0.5)",
    )
    args = parser.parse_args()

    src_norm = normalize(_source_text(args.source))
    src_shingles = _shingles(src_norm.split())
    items = _held_out_items()
    if not items:
        print("no held-out corpus found; nothing to check", file=sys.stderr)
        sys.exit(2)

    leaks: list[tuple[float, bool, str, str]] = []
    for iid, question in items:
        ish = _shingles(_tokens(question))
        containment = (len(ish & src_shingles) / len(ish)) if ish else 0.0
        exact = normalize(question) in src_norm
        if containment >= args.threshold or exact:
            leaks.append((containment, exact, iid, question))

    leaks.sort(reverse=True, key=lambda r: r[0])
    print(
        f"source={args.source!r} held-out items={len(items)} "
        f"source-shingles={len(src_shingles):,} threshold={args.threshold}"
    )
    if leaks:
        print(f"LEAKAGE: {len(leaks)} held-out item(s) reproduced in the source:")
        for containment, exact, iid, question in leaks[:25]:
            mark = "EXACT" if exact else "     "
            print(f"  {containment:.2f} {mark} {iid:18s} {question[:70]}")
        if len(leaks) > 25:
            print(f"  ... and {len(leaks) - 25} more")
        print(
            "\nDo NOT use this source for generation: it contains held-out test "
            "items, which would inflate scores (rubric automatic fail)."
        )
        sys.exit(1)
    print("clean: no held-out item (or near-copy) found in the source")


if __name__ == "__main__":
    main()
