# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Seed the local sync server with a shared collection and print the login hkey.

This is the desktop/server side of local phone<->desktop sync. It:
  1. builds the tagged Exam P deck in a throwaway collection (or, with
     ``--from-collection PATH``, uploads an EXISTING collection such as the
     seeded demo persona so the phone downloads a fully-scored collection),
  2. logs in to the running local sync server (tools/speedrun/sync_server.sh),
  3. full-uploads it so the server has a shared collection, and
  4. prints the hkey + endpoint.

The printed hkey can be written straight into AnkiDroid's SharedPreferences
(keys: syncBaseUrl, syncBaseUrl_switch, username, hkey) and into the desktop
profile, so BOTH clients authenticate to the local server with no UI login.

Run the server first, then either:

    # plain Exam P deck (no history -> phone shows the honest abstain state)
    PYTHONPATH=pylib:out/pylib out/pyenv/bin/python tools/speedrun/sync_setup.py

    # the fully-scored synthetic persona (phone shows all three scores + ranges)
    make seed-persona
    PYTHONPATH=pylib:out/pylib out/pyenv/bin/python \
        tools/speedrun/sync_setup.py --from-collection out/demo-persona.anki2

Any of the three mock-user scenarios can be pushed the same way (the Makefile
wraps them as ``make sync-seed-persona`` / ``sync-seed-persona-new`` /
``sync-seed-persona-experienced``). The phone holds one collection at a time, so
re-run a different target and re-sync the phone to swap scenarios; each upload
force-replaces whatever the server was holding.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import time

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [os.path.join(_REPO, "pylib"), os.path.join(_REPO, "out", "pylib")]

import anki.collection  # noqa: E402,F401  (preload to avoid circular import)
from anki.collection import Collection  # noqa: E402
from anki.speedrun.seed import build_deck  # noqa: E402

ENDPOINT = os.environ.get("SYNC_ENDPOINT", "http://127.0.0.1:27701/")
USER = os.environ.get("SYNC_USER", "user")
PASS = os.environ.get("SYNC_PASS", "pass")


def _login_with_retry(col: Collection, endpoint: str, timeout: float = 20.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            return col.sync_login(USER, PASS, endpoint)
        except Exception as exc:  # noqa: BLE001 - server may still be booting
            last = exc
            time.sleep(0.3)
    raise RuntimeError(f"could not log in to sync server {endpoint}: {last}")


def do_sync(col: Collection, auth, force_upload: bool = False) -> str:
    """One sync, handling the full up/down handshake exactly like the desktop.

    ``force_upload`` makes this collection become the server's collection even if
    the server already holds a different one (used when re-seeding the server with
    the persona over a previously-uploaded plain deck).
    """
    if force_upload:
        col.close_for_full_sync()
        col.full_upload_or_download(auth=auth, server_usn=None, upload=True)
        col.reopen(after_full_sync=True)
        return "full_upload"
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from-collection",
        metavar="PATH",
        help="upload an existing .anki2 (e.g. out/demo-persona.anki2) instead of "
        "building a fresh Exam P deck; force-uploads so it replaces the server's "
        "collection",
    )
    args = parser.parse_args()

    work = tempfile.mkdtemp(prefix="speedrun-sync-seed-")
    seed_path = os.path.join(work, "seed.anki2")
    force_upload = False
    if args.from_collection:
        src = os.path.abspath(args.from_collection)
        if not os.path.exists(src):
            print(f"FAIL: --from-collection not found: {src}")
            return 1
        # Copy so the original stays pristine; sync mutates the collection (USN).
        shutil.copyfile(src, seed_path)
        col = Collection(seed_path)
        cards = col.db.scalar("select count() from cards") or 0
        force_upload = True  # replace whatever the server currently holds
    else:
        col = Collection(seed_path)
        cards = build_deck(col)
    try:
        notes = col.db.scalar("select count() from notes") or 0
        revlog = col.db.scalar("select count() from revlog") or 0
        auth = _login_with_retry(col, ENDPOINT)
        action = do_sync(col, auth, force_upload=force_upload)
        # Verify the server now has it: a fresh client should full-download it.
        verify = Collection(os.path.join(work, "verify.anki2"))
        try:
            v_auth = verify.sync_login(USER, PASS, ENDPOINT)
            v_action = do_sync(verify, v_auth)
            v_notes = verify.db.scalar("select count() from notes") or 0
            v_revlog = verify.db.scalar("select count() from revlog") or 0
        finally:
            verify.close()
        print("=== sync setup ===")
        print(
            f"seeded : {cards} cards / {notes} notes / {revlog} revlog  "
            f"(upload action={action})"
        )
        print(
            f"verify : fresh client action={v_action}, notes={v_notes}, revlog={v_revlog}"
        )
        print(f"HKEY={auth.hkey}")
        print(f"ENDPOINT={auth.endpoint or ENDPOINT}")
        print(f"USER={USER}")
        ok = (
            action == "full_upload"
            and v_action == "full_download"
            and v_notes == notes
            and v_revlog == revlog
        )
        print(f"RESULT={'OK' if ok else 'CHECK'}")
        return 0 if ok else 1
    finally:
        col.close()


if __name__ == "__main__":
    raise SystemExit(main())
