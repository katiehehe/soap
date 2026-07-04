"""Print an auth hkey for the local sync server (login only — no seeding).

Used by tools/speedrun/phone_sync_config.sh to authenticate AnkiDroid without a
UI login. The built-in server derives a stable hkey from the username, so this
is safe to call repeatedly.

  PYTHONPATH=pylib:out/pylib out/pyenv/bin/python tools/speedrun/sync_hkey.py
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
    col = Collection(os.path.join(tempfile.mkdtemp(prefix="hkey-"), "h.anki2"))
    try:
        print(col.sync_login(USER, PASS, ENDPOINT).hkey)
    finally:
        col.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
