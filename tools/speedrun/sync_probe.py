"""Download the current server collection into a throwaway client and report
note/card/review counts. Used to verify sync (e.g. reviews done on the phone
show up on the server after it syncs).

  PYTHONPATH=pylib:out/pylib out/pyenv/bin/python tools/speedrun/sync_probe.py
"""

from __future__ import annotations

import os
import sys
import tempfile

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [os.path.join(_REPO, "pylib"), os.path.join(_REPO, "out", "pylib")]

import anki.collection  # noqa: E402,F401
from anki.collection import Collection  # noqa: E402

ENDPOINT = os.environ.get("SYNC_ENDPOINT", "http://127.0.0.1:27701/")
USER = os.environ.get("SYNC_USER", "user")
PASS = os.environ.get("SYNC_PASS", "pass")


def main() -> int:
    work = tempfile.mkdtemp(prefix="speedrun-sync-probe-")
    col = Collection(os.path.join(work, "probe.anki2"))
    try:
        auth = col.sync_login(USER, PASS, ENDPOINT)
        out = col.sync_collection(auth, False)
        resp = out.__class__
        if out.required != resp.NO_CHANGES:
            col.close_for_full_sync()
            col.full_upload_or_download(auth=auth, server_usn=None, upload=False)
            col.reopen(after_full_sync=True)
        notes = col.db.scalar("select count() from notes") or 0
        cards = col.db.scalar("select count() from cards") or 0
        revlog = col.db.scalar("select count() from revlog") or 0
        print(f"NOTES={notes} CARDS={cards} REVLOG={revlog}")
    finally:
        col.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
