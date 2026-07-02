#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Leakage scan (challenge 7e).

Splits items into train/test with a fixed seed and flags any test item that also
appears in training (verbatim or near-copy). Exits non-zero on leakage, so it can
be wired as a pre-commit / CI gate.

Usage:
    out/pyenv/bin/python tools/speedrun/leakage_scan.py --collection col.anki2
    out/pyenv/bin/python tools/speedrun/leakage_scan.py --items items.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _p in (os.path.join(_REPO, "pylib"), os.path.join(_REPO, "out", "pylib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from anki.collection import Collection  # noqa: E402
from anki.speedrun.evalsplit import find_leaks, train_test_split  # noqa: E402


def items_from_collection(path: str) -> list[tuple[str, str]]:
    col = Collection(path)
    items: list[tuple[str, str]] = []
    for nid in col.find_notes("tag:subtopic::*"):
        note = col.get_note(nid)
        items.append((str(nid), note["Front"]))
    col.close()
    return items


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--collection")
    parser.add_argument("--items", help="JSON list of {id, text}")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--test-frac", type=float, default=0.2)
    parser.add_argument("--threshold", type=float, default=0.9)
    args = parser.parse_args()

    if args.items:
        with open(args.items, encoding="utf8") as file:
            data = json.load(file)
        items = [(str(d["id"]), d["text"]) for d in data]
    elif args.collection:
        items = items_from_collection(args.collection)
    else:
        print("provide --collection or --items", file=sys.stderr)
        sys.exit(2)

    id_to_text = dict(items)
    train_ids, test_ids = train_test_split(
        [i for i, _ in items], args.test_frac, args.seed
    )
    train = [(i, id_to_text[i]) for i in train_ids]
    test = [(i, id_to_text[i]) for i in test_ids]
    leaks = find_leaks(train, test, args.threshold)

    print(f"seed={args.seed} items={len(items)} train={len(train)} test={len(test)}")
    if leaks:
        print(f"LEAKAGE: {len(leaks)} test item(s) found in training:")
        for leak in leaks:
            print(
                f"  test {leak.test_id} ~ train {leak.train_id} "
                f"(sim={leak.similarity:.2f})"
            )
        sys.exit(1)
    print("clean: no test items or near-copies found in training data")


if __name__ == "__main__":
    main()
