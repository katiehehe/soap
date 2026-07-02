#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Practice-test mode demo (score-model Step 3, Readiness).

    make practice-test

Builds a throwaway collection, gives it a synthetic-persona study history (enough
graded reviews + coverage to clear the give-up gate), then assembles a
section-weighted practice test, has the persona answer it, grades it, records it,
and prints the readiness band the engine emits. Everything is seeded and
reproducible; every number is real-engine output over the clearly-labelled
synthetic persona.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time

_REPO = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
for _p in (os.path.join(_REPO, "pylib"), os.path.join(_REPO, "out", "pylib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from anki import speedrun_pb2  # noqa: E402
from anki.collection import Collection  # noqa: E402
from anki.speedrun import expected_subtopic_tags, unit_weights  # noqa: E402
from anki.speedrun.persona import (  # noqa: E402
    SYNTHETIC_LABEL,
    answer_items,
    default_persona,
    review_grades,
)
from anki.speedrun.practice_test import (  # noqa: E402
    assemble_test,
    grade,
    practice_stats,
    record_test,
)
from anki.speedrun.seed import build_deck  # noqa: E402
from anki.speedrun.soa_sample import load_corpus  # noqa: E402


def _seed_reviews(col: Collection, persona, per_subtopic: int = 14) -> None:
    sql = "insert into revlog (id,cid,usn,ease,ivl,lastIvl,factor,time,type) values (?,?,?,?,?,?,?,?,?)"
    rid = int(time.time() * 1000) - 400_000_000
    rows = []
    for tag in expected_subtopic_tags():
        cids = col.find_cards(f'"tag:{tag}"')
        if not cids:
            continue
        for i, ease in enumerate(review_grades(persona, tag, per_subtopic)):
            rows.append((rid, cids[i % len(cids)], -1, ease, 1, 1, 2500, 1000, 1))
            rid += 1
    col.db.executemany(sql, rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tests", type=int, default=4)
    parser.add_argument("--size", type=int, default=30)
    args = parser.parse_args()

    corpus = load_corpus()
    persona = default_persona()
    print(
        f"corpus: {corpus.source} ({'official SOA' if corpus.is_real_soa else 'original fallback'})"
    )
    print(f"persona: {persona.name!r} ({SYNTHETIC_LABEL}, seed {persona.seed})\n")

    path = os.path.join(tempfile.mkdtemp(prefix="speedrun-practice-"), "col.anki2")
    col = Collection(path)
    try:
        build_deck(col)
        _seed_reviews(col, persona)
        last = None
        for t in range(args.tests):
            test = assemble_test(n=args.size, seed=2000 + t, items=corpus.items)
            responses = {
                r.item_id: r.correct
                for r in answer_items(persona, test, seed_salt=f"demo-{t}")
            }
            last = grade(test, responses, label=SYNTHETIC_LABEL)
            record_test(col, last)

        print(
            f"assembled {args.tests} section-weighted tests of {args.size} questions."
        )
        if last is not None:
            print("last test per-unit (correct/total):")
            for uid, _w in unit_weights():
                c, tot = last.per_unit.get(uid, (0, 0))
                print(f"  {uid:<13} {c}/{tot}")
        totals = practice_stats(col)
        print(
            f"\ncumulative practice evidence: {totals['correct']}/{totals['questions']} correct over {totals['tests']} tests"
        )

        units = [
            speedrun_pb2.UnitWeight(unit_id=u, weight=w) for u, w in unit_weights()
        ]
        result = col._backend.compute_readiness(
            expected_subtopics=expected_subtopic_tags(), units=units
        )
        if result.WhichOneof("value") == "score":
            s = result.score
            print("\nReadiness (synthetic demo persona):")
            print(f"  projected 0-10 : {s.point:.1f}  (range {s.low:.1f}-{s.high:.1f})")
            print(f"  P(pass)        : {s.pass_probability:.0%}")
            print(
                f"  coverage       : {s.coverage_pct:.0%}   confidence {s.confidence:.2f}"
            )
            for r in s.reasons:
                print(f"  - {r}")
            print(f"  next best      : {s.next_best_action}")
        else:
            ns = result.no_score
            print(f"\nReadiness: NoScore (give-up rule) — {ns.reason}")
    finally:
        col.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
