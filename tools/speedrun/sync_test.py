#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Two-way sync test (rubric 7b) against Anki's built-in sync server.

    make sync-test

We do NOT rewrite sync. This starts Anki's own sync server
(`anki.syncserver`, the same Rust sync protocol the phone build uses), then
drives TWO client collections through it to prove reviews flow both ways with no
loss or double-counting:

1. A base collection uploads the tagged Exam P deck.
2. Two clients ("desktop" and "phone") full-download it, so they share one
   collection.
3. OFFLINE, each reviews a DIFFERENT set of 10 cards.
4. They sync; we assert all 20 reviews land once on both sides (revlog
   reconciliation), none lost, none doubled.
5. Same-card conflict: both review the SAME card offline, then sync; we record
   the deterministic winner (documented in docs/sync-conflict-rule.md).

The phone runs this exact engine, so desktop<->desktop here exercises the same
sync code path; the on-device phone<->desktop demo is a manual recording (see
docs/demo-script.md).
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from typing import Literal

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _p in (os.path.join(_REPO, "pylib"), os.path.join(_REPO, "out", "pylib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from anki.cards import CardId  # noqa: E402
from anki.collection import Collection  # noqa: E402
from anki.speedrun.seed import build_deck  # noqa: E402

USER, PASS = "user", "pass"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _start_server(base: str, port: int) -> subprocess.Popen:
    env = dict(os.environ)
    env.update(
        SYNC_HOST="127.0.0.1",
        SYNC_PORT=str(port),
        SYNC_BASE=base,
        SYNC_USER1=f"{USER}:{PASS}",
        RUST_LOG="error",
    )
    return subprocess.Popen(
        [os.path.join(_REPO, "out", "pyenv", "bin", "python"), "-m", "anki.syncserver"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _login_with_retry(col: Collection, endpoint: str, timeout: float = 20.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            return col.sync_login(USER, PASS, endpoint)
        except Exception as exc:  # noqa: BLE001 - server still booting
            last = exc
            time.sleep(0.3)
    raise RuntimeError(f"sync server did not come up: {last}")


def do_sync(col: Collection, auth) -> str:
    """One sync, handling the full up/down handshake exactly like the desktop."""
    out = col.sync_collection(auth, False)
    resp = out.__class__
    if out.required == resp.NO_CHANGES:
        return "normal"
    if out.required == resp.FULL_DOWNLOAD:
        col.close_for_full_sync()
        col.full_upload_or_download(auth=auth, server_usn=None, upload=False)
        col.reopen(after_full_sync=True)
        return "full_download"
    # FULL_UPLOAD or FULL_SYNC (both-changed): first sync from an empty server.
    col.close_for_full_sync()
    col.full_upload_or_download(auth=auth, server_usn=None, upload=True)
    col.reopen(after_full_sync=True)
    return "full_upload"


def revlog_count(col: Collection) -> int:
    return col.db.scalar("select count() from revlog") or 0


def answer_cards(
    col: Collection, card_ids: Sequence[CardId], ease: Literal[1, 2, 3, 4] = 3
) -> int:
    n = 0
    for cid in card_ids:
        card = col.get_card(cid)
        card.start_timer()  # answerCard() reads the review timer
        col.sched.answerCard(card, ease)
        n += 1
        # Space reviews so each gets a distinct millisecond revlog id, as real
        # reviews (seconds apart) do; otherwise a microsecond-tight loop produces
        # colliding ids that look like "lost" reviews.
        time.sleep(0.005)
    return n


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviews", type=int, default=10)
    args = parser.parse_args()
    n = args.reviews

    work = tempfile.mkdtemp(prefix="speedrun-sync-")
    port = _free_port()
    endpoint = f"http://127.0.0.1:{port}/"
    server = _start_server(os.path.join(work, "server"), port)

    ok = True
    try:
        # 1. Base collection uploads the deck.
        base = Collection(os.path.join(work, "base.anki2"))
        build_deck(base)
        auth = _login_with_retry(base, endpoint)
        print(f"base first sync: {do_sync(base, auth)}")
        base_reviews = revlog_count(base)
        base.close()

        # 2. Two clients download the shared collection.
        desktop = Collection(os.path.join(work, "desktop.anki2"))
        phone = Collection(os.path.join(work, "phone.anki2"))
        print(
            f"desktop download: {do_sync(desktop, desktop.sync_login(USER, PASS, endpoint))}"
        )
        print(
            f"phone download:   {do_sync(phone, phone.sync_login(USER, PASS, endpoint))}"
        )

        cards = sorted(desktop.find_cards("deck:*"))
        assert len(cards) >= 2 * n, f"need >= {2 * n} cards, have {len(cards)}"

        # 3. OFFLINE: each reviews a DIFFERENT set of n cards.
        d_ids, p_ids = cards[:n], cards[n : 2 * n]
        answer_cards(desktop, d_ids)
        answer_cards(phone, p_ids)

        # 4. Sync both ways: phone first, desktop pulls phone's, phone pulls desktop's.
        d_auth = desktop.sync_login(USER, PASS, endpoint)
        p_auth = phone.sync_login(USER, PASS, endpoint)
        do_sync(desktop, d_auth)
        do_sync(phone, p_auth)
        do_sync(desktop, d_auth)

        d_total = revlog_count(desktop) - base_reviews
        p_total = revlog_count(phone) - base_reviews
        expected = 2 * n
        print("\n=== revlog reconciliation (7b) ===")
        print(f"reviewed offline : desktop {n} + phone {n} = {expected}")
        print(
            f"after sync       : desktop {d_total} | phone {p_total} (expected {expected} each)"
        )
        landed = d_total == expected and p_total == expected
        print(f"none lost/doubled: {'PASS' if landed else 'FAIL'}")
        ok = ok and landed

        # 5. Same-card conflict: both review the SAME card offline, then sync.
        conflict = cards[2 * n]
        answer_cards(desktop, [conflict], ease=4)  # Easy on desktop
        # Card mtime is in whole seconds; space the conflicting review >1s later
        # so the later review is an unambiguous winner (as real cross-device
        # reviews, minutes apart, are). A same-second tie has no natural winner.
        time.sleep(1.1)
        answer_cards(phone, [conflict], ease=1)  # Again on phone (later -> wins)
        # Sync both to a stable state (NO_CHANGES on both), so convergence is
        # tested, not sync ordering.
        for _ in range(3):
            do_sync(desktop, d_auth)
            do_sync(phone, p_auth)
        # Both graded reviews are preserved in the revlog (nothing dropped); the
        # card's final scheduling state converges to a single deterministic
        # winner (Anki's newer-mtime-wins on the card record). See
        # docs/sync-conflict-rule.md.
        d_conflict_rows = desktop.db.scalar(
            "select count() from revlog where cid = ?", conflict
        )
        both_kept = d_conflict_rows == 2
        d_state = desktop.get_card(conflict)
        p_state = phone.get_card(conflict)
        agree = (d_state.queue, d_state.type, d_state.due) == (
            p_state.queue,
            p_state.type,
            p_state.due,
        )
        print("\n=== same-card conflict ===")
        print(
            f"both reviews kept in revlog: {'PASS' if both_kept else 'FAIL'} ({d_conflict_rows} rows)"
        )
        print(
            f"deterministic winner on both sides: {'PASS' if agree else 'FAIL'} "
            f"(desktop q={d_state.queue}/due={d_state.due}, phone q={p_state.queue}/due={p_state.due})"
        )
        ok = ok and both_kept and agree

        desktop.close()
        phone.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()

    print(f"\nSYNC TEST: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
