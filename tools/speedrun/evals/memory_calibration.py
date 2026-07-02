#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Memory-model (FSRS) calibration on held-out reviews (score-model Step 1).

The memory signal IS Anki's FSRS. This reports how well-calibrated it is on the
collection's own review history using the engine's *time-series (held-out)*
evaluation: log loss and RMSE over the reliability bins. Both are computed by the
FSRS library's proper replay, so the number is real, not hand-rolled.

Honest by construction: with too few graded reviews (or FSRS disabled) it prints
an explicit "not enough data yet" and NO number (the give-up rule applied to
calibration). It never reads or writes the readiness score.

Usage:
    out/pyenv/bin/python tools/speedrun/evals/memory_calibration.py \
        [--col PATH] [--min-reviews N] [--search TEXT]

With no --col it builds the (unreviewed) seed deck in a temp collection to
demonstrate the give-up path; point --col at a real .anki2 with study history to
get actual calibration numbers. Deterministic given the collection + FSRS params.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile

_REPO = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
for _p in (os.path.join(_REPO, "pylib"), os.path.join(_REPO, "out", "pylib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from anki.collection import Collection  # noqa: E402
from anki.speedrun.seed import build_deck  # noqa: E402


def graded_review_count(col: Collection) -> int:
    return int(col.db.scalar("select count() from revlog where ease > 0") or 0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--col", help="path to a .anki2 collection with review history")
    parser.add_argument("--min-reviews", type=int, default=100)
    parser.add_argument(
        "--search", default="", help="Anki search limiting which cards are evaluated"
    )
    args = parser.parse_args()

    tmpdir = None
    if args.col:
        col = Collection(args.col)
    else:
        tmpdir = tempfile.mkdtemp()
        col = Collection(os.path.join(tmpdir, "collection.anki2"))
        build_deck(col)

    try:
        n = graded_review_count(col)
        print(f"Graded reviews on file: {n}")

        if n < args.min_reviews:
            print(
                f"NOT ENOUGH DATA: memory calibration needs >= {args.min_reviews} "
                f"graded reviews; have {n}."
            )
            print("No calibration number is shown (honesty / give-up rule).")
            return 0

        try:
            resp = col._backend.evaluate_params(
                search=args.search,
                ignore_revlogs_before_ms=0,
                num_of_relearning_steps=1,
            )
        except Exception as exc:  # noqa: BLE001 - report, never fabricate
            print(f"NOT ENOUGH DATA: FSRS held-out evaluation could not run ({exc}).")
            print("No calibration number is shown (honesty / give-up rule).")
            return 0

        print("Memory model = FSRS. Held-out (time-series split) calibration:")
        print(f"  log loss  : {resp.log_loss:.4f}   (lower is better)")
        print(
            f"  RMSE(bins): {resp.rmse_bins:.4f}   (reliability-curve error, lower better)"
        )
        print("Reproducible: deterministic given the collection + FSRS params.")
        return 0
    finally:
        col.close()


if __name__ == "__main__":
    raise SystemExit(main())
