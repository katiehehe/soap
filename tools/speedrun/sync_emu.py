#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Desktop-side driver for the on-device phone<->desktop sync validation.

This is the "desktop" half of the real two-way sync test (rubric 7b): it drives a
persistent headless collection on the SAME compiled Rust engine the phone build
uses, talking to the SAME local sync server (`make sync-server`) that the
AnkiDroid emulator syncs to. Pair it with adb driving the real emulator (the
"phone") to prove reviews flow both ways with no loss / double-count.

We deliberately do NOT open the running desktop GUI app's collection (that would
require a second writer on the same DB). Using a dedicated collection on the same
engine is the reproducible, safe way to be the desktop peer.

Commands
--------
    sync            one sync (handles first-time full download), print result
    status          card count, revlog count, per-deck due, last few revlog rows
    review N        answer N due cards (ease configurable), WITHOUT syncing
    review-card CID answer one specific card by id
    card CID        print one card's scheduling state (queue/type/due/mod)
    reset           delete the local desktop collection (fresh peer next sync)

Endpoint / account come from the same defaults as sync_server.sh (user:pass on
http://127.0.0.1:27701/); override with SYNC_ENDPOINT / SYNC_USER / SYNC_PASS.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from collections.abc import Sequence
from typing import Literal

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _p in (os.path.join(_REPO, "pylib"), os.path.join(_REPO, "out", "pylib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import anki.collection  # noqa: E402,F401
from anki.cards import CardId  # noqa: E402
from anki.collection import Collection  # noqa: E402
from anki.decks import DeckId  # noqa: E402

ENDPOINT = os.environ.get("SYNC_ENDPOINT", "http://127.0.0.1:27701/")
USER = os.environ.get("SYNC_USER", "user")
PASS = os.environ.get("SYNC_PASS", "pass")
COL_PATH = os.environ.get(
    "SYNC_EMU_COL", os.path.join(_REPO, "out", "sync-emu", "desktop.anki2")
)


def _open() -> Collection:
    os.makedirs(os.path.dirname(COL_PATH), exist_ok=True)
    return Collection(COL_PATH)


def _login(col: Collection):
    return col.sync_login(USER, PASS, ENDPOINT)


def do_sync(col: Collection, auth) -> str:
    """One sync, handling the full up/down handshake exactly like the desktop."""
    out = col.sync_collection(auth, False)
    resp = out.__class__
    if out.required == resp.NO_CHANGES:
        return "normal (no changes)"
    if out.required == resp.NORMAL_SYNC:
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


def revlog_count(col: Collection) -> int:
    return col.db.scalar("select count() from revlog") or 0


def answer_cards(
    col: Collection, card_ids: Sequence[CardId], ease: Literal[1, 2, 3, 4] = 3
) -> list[int]:
    done = []
    for cid in card_ids:
        card = col.get_card(cid)
        card.start_timer()
        col.sched.answerCard(card, ease)
        done.append(int(cid))
        time.sleep(0.02)  # distinct ms revlog ids, as real reviews are
    return done


def cmd_status(col: Collection) -> None:
    ncards = col.db.scalar("select count() from cards") or 0
    nnotes = col.db.scalar("select count() from notes") or 0
    nrev = revlog_count(col)
    print(f"collection: {COL_PATH}")
    print(f"notes={nnotes} cards={ncards} revlog_rows={nrev}")
    print("decks (due today = new+lrn+rev):")
    for d in col.decks.all_names_and_ids(skip_empty_default=True):
        tree = col.sched.deck_due_tree(DeckId(d.id))
        if tree:
            print(
                f"  [{d.id}] {d.name}: new={tree.new_count} lrn={tree.learn_count} rev={tree.review_count}"
            )
    rows = col.db.all("select id, cid, ease, type from revlog order by id desc limit 6")
    if rows:
        print("last revlog rows (id ms, cid, ease, type):")
        for r in rows:
            print(f"  {r[0]}  cid={r[1]} ease={r[2]} type={r[3]}")


def cmd_card(col: Collection, cid: int) -> None:
    c = col.get_card(CardId(cid))
    print(
        f"card {cid}: queue={c.queue} type={c.type} due={c.due} ivl={c.ivl} "
        f"reps={c.reps} lapses={c.lapses} mod={c.mod}"
    )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sync")
    sub.add_parser("status")
    rv = sub.add_parser("review")
    rv.add_argument("n", type=int)
    rv.add_argument("--ease", type=int, default=3, choices=[1, 2, 3, 4])
    rc = sub.add_parser("review-card")
    rc.add_argument("cid", type=int)
    rc.add_argument("--ease", type=int, default=3, choices=[1, 2, 3, 4])
    cd = sub.add_parser("card")
    cd.add_argument("cid", type=int)
    sub.add_parser("reset")
    args = p.parse_args()

    if args.cmd == "reset":
        for suf in ("", "-wal", "-shm"):
            try:
                os.remove(COL_PATH + suf)
            except FileNotFoundError:
                pass
        media = COL_PATH.replace(".anki2", ".media")
        shutil.rmtree(media, ignore_errors=True)
        print(f"removed {COL_PATH}")
        return 0

    col = _open()
    try:
        if args.cmd == "sync":
            auth = _login(col)
            print(f"sync: {do_sync(col, auth)}")
            cmd_status(col)
        elif args.cmd == "status":
            cmd_status(col)
        elif args.cmd == "review":
            due = sorted(col.find_cards("deck:* is:due"))
            if not due:
                due = sorted(col.find_cards("deck:*"))
            ids = answer_cards(col, due[: args.n], ease=args.ease)
            print(f"reviewed {len(ids)} cards (ease={args.ease}): {ids}")
        elif args.cmd == "review-card":
            ids = answer_cards(col, [CardId(args.cid)], ease=args.ease)
            print(f"reviewed card {ids} (ease={args.ease})")
        elif args.cmd == "card":
            cmd_card(col, args.cid)
    finally:
        col.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
