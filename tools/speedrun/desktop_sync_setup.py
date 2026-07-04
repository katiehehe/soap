"""Point the desktop at the local sync server and pull the shared collection.

Run with the desktop app CLOSED. It:
  1. sets customSyncUrl + syncUser + syncKey in the desktop profile (so the GUI
     Sync button works against the local server), and
  2. full-downloads the server's collection so the desktop shares it with the
     phone.

Back up the collection first (tools do this); a full download replaces the local
collection with the server's.
"""

from __future__ import annotations

import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [
    os.path.join(_REPO, p) for p in ("pylib", "out/pylib", "qt", "out/qt")
]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import anki.collection  # noqa: E402,F401
from anki.collection import Collection  # noqa: E402

ENDPOINT = os.environ.get("SYNC_ENDPOINT", "http://127.0.0.1:27701/")
USER = os.environ.get("SYNC_USER", "user")
PASS = os.environ.get("SYNC_PASS", "pass")
BASE = os.environ.get(
    "ANKI_BASE", os.path.expanduser("~/Library/Application Support/Anki2")
)


def _download(col: Collection, auth) -> str:
    """Adopt the server's collection (full download), regardless of handshake."""
    out = col.sync_collection(auth, False)
    resp = out.__class__
    if out.required == resp.NO_CHANGES:
        return "normal (already in sync)"
    col.close_for_full_sync()
    col.full_upload_or_download(auth=auth, server_usn=None, upload=False)
    col.reopen(after_full_sync=True)
    return "full_download"


def main() -> int:
    from aqt.profiles import ProfileManager

    pm = ProfileManager(base=BASE)
    pm.setupMeta()
    names = pm.profiles()
    name = "User 1" if "User 1" in names else names[0]
    pm.load(name)
    pm.set_custom_sync_url(ENDPOINT)
    pm.set_sync_username(USER)

    col_path = os.path.join(BASE, name, "collection.anki2")
    col = Collection(col_path)
    try:
        auth = col.sync_login(USER, PASS, ENDPOINT)
        pm.set_sync_key(auth.hkey)
        pm.save()
        action = _download(col, auth)
        notes = col.db.scalar("select count() from notes") or 0
    finally:
        col.close()

    print(f"profile          : {name}")
    print(f"customSyncUrl    : {ENDPOINT}")
    print(f"syncUser / hkey  : {USER} / {auth.hkey[:8]}...")
    print(f"sync action      : {action}")
    print(f"notes on desktop : {notes}")
    print(f"RESULT={'OK' if notes > 0 else 'CHECK'}")
    return 0 if notes > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
