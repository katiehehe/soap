# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Two-way sync check through the LIVE local server (the one the emulator uses).

Two clients each download the shared collection, review a DIFFERENT set of cards
offline, then sync. Asserts every review lands on BOTH clients with none lost or
doubled, so reviews flow both directions (rubric 7b), against the actual
running server (default http://127.0.0.1:27701/), not an ephemeral one.

  make sync-server   # in another terminal, first
  PYTHONPATH=pylib:out/pylib out/pyenv/bin/python tools/speedrun/sync_twoway_check.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from typing import Literal

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [os.path.join(_REPO, "pylib"), os.path.join(_REPO, "out", "pylib")]

import anki.collection  # noqa: E402,F401
from anki.collection import Collection  # noqa: E402

ENDPOINT = os.environ.get("SYNC_ENDPOINT", "http://127.0.0.1:27701/")
USER = os.environ.get("SYNC_USER", "user")
PASS = os.environ.get("SYNC_PASS", "pass")
N = int(os.environ.get("REVIEWS", "3"))


def do_sync(col: Collection, auth) -> str:
    out = col.sync_collection(auth, False)
    resp = out.__class__
    if out.required == resp.NO_CHANGES:
        return "normal"
    if out.required == resp.FULL_DOWNLOAD:
        col.close_for_full_sync()
        col.full_upload_or_download(auth=auth, server_usn=None, upload=False)
        col.reopen(after_full_sync=True)
        return "full_download"
    col.close_for_full_sync()
    col.full_upload_or_download(auth=auth, server_usn=None, upload=True)
    col.reopen(after_full_sync=True)
    return "full_upload"


def revlog(col: Collection) -> int:
    return col.db.scalar("select count() from revlog") or 0


def answer(col: Collection, ids, ease: Literal[1, 2, 3, 4] = 3) -> None:
    for cid in ids:
        card = col.get_card(cid)
        card.start_timer()
        col.sched.answerCard(card, ease)
        time.sleep(0.005)  # distinct-millisecond revlog ids, like real reviews


def main() -> int:
    work = tempfile.mkdtemp(prefix="speedrun-twoway-")
    a = Collection(os.path.join(work, "a.anki2"))
    b = Collection(os.path.join(work, "b.anki2"))
    try:
        do_sync(a, a.sync_login(USER, PASS, ENDPOINT))
        do_sync(b, b.sync_login(USER, PASS, ENDPOINT))
        base = revlog(a)
        cards = sorted(a.find_cards("deck:*"))
        if len(cards) < 2 * N:
            print(f"FAIL: need >= {2 * N} cards, server has {len(cards)}")
            return 1
        a_ids, b_ids = cards[:N], cards[N : 2 * N]
        answer(a, a_ids)  # client A reviews its N cards offline
        answer(b, b_ids)  # client B reviews a DIFFERENT N cards offline
        a_auth = a.sync_login(USER, PASS, ENDPOINT)
        b_auth = b.sync_login(USER, PASS, ENDPOINT)
        do_sync(a, a_auth)  # A -> server
        do_sync(b, b_auth)  # B -> server, pulls A's
        do_sync(a, a_auth)  # A pulls B's
        a_total, b_total = revlog(a) - base, revlog(b) - base
        expected = 2 * N
        print(f"reviewed offline : A {N} + B {N} = {expected}")
        print(
            f"after sync       : A {a_total} | B {b_total}  (expected {expected} each)"
        )
        ok = a_total == expected and b_total == expected
        print(f"TWO-WAY SYNC: {'PASS' if ok else 'FAIL'}  ({ENDPOINT})")
        return 0 if ok else 1
    finally:
        a.close()
        b.close()


if __name__ == "__main__":
    raise SystemExit(main())
