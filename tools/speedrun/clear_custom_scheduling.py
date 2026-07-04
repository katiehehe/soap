#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Clear stray Anki "Custom scheduling" JavaScript from a collection.

    python tools/speedrun/clear_custom_scheduling.py                 # default profile
    python tools/speedrun/clear_custom_scheduling.py --path /path/collection.anki2
    python tools/speedrun/clear_custom_scheduling.py --dry-run

Why this exists
---------------
Anki's v3 scheduler can run a per-collection "Custom scheduling" snippet (stored
in the collection config key ``cardStateCustomizer``). It is injected into the
reviewer as ``anki.mutateNextCardStates(...)`` and runs on EVERY card. This fork
does NOT use custom scheduling — the three-tier mastery scheduler lives in the
Rust engine and is toggled by a config flag — so that field should be empty.

If it contains leftover/experimental code it breaks review in two visible ways:

  * a JS error on every card (e.g. ``ReferenceError: hello is not defined``), and
  * the modal **"Unexpected API access. Please report this message on the Anki
    forums."** whenever that card JS touches the ``/_anki/`` backend, because
    Anki (by design) blocks untrusted card/scheduling JS from the backend API.

This clears the key through Anki's own API, so FSRS intervals and undo are
untouched and the collection is never corrupted. Anki must be CLOSED first
(it holds an exclusive lock and caches config in memory).
"""

from __future__ import annotations

import argparse
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _p in (os.path.join(_REPO, "pylib"), os.path.join(_REPO, "out", "pylib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import anki.collection  # noqa: E402,F401  (preload to avoid a circular import)
from anki.collection import Collection  # noqa: E402

_CONFIG_KEY = "cardStateCustomizer"


def _default_collection_path() -> str:
    """Best-effort path to the desktop profile's collection (macOS/Linux/Windows)."""
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support/Anki2")
    elif os.name == "nt":
        base = os.path.join(os.environ.get("APPDATA", ""), "Anki2")
    else:
        base = os.path.expanduser("~/.local/share/Anki2")
    return os.path.join(base, "User 1", "collection.anki2")


def clear(path: str, *, dry_run: bool) -> int:
    if not os.path.exists(path):
        print(f"collection not found: {path}", file=sys.stderr)
        return 2
    try:
        col = Collection(path)
    except Exception as exc:  # pragma: no cover - lock/other IO errors
        print(f"could not open collection (is Anki still running?): {exc}", file=sys.stderr)
        return 2
    try:
        current = col.get_config(_CONFIG_KEY, None)
        if not current:
            print(f"'{_CONFIG_KEY}' is already empty — nothing to do.")
            return 0
        print(f"current custom scheduling code:\n  {current!r}")
        if dry_run:
            print("dry run: not modifying the collection.")
            return 0
        # Empty string is the documented "no custom scheduling" value.
        # set_config writes through to the DB immediately; close() flushes.
        col.set_config(_CONFIG_KEY, "")
        print(f"cleared '{_CONFIG_KEY}'. Sync to push the fix to the phone too.")
        return 0
    finally:
        col.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--path",
        default=_default_collection_path(),
        help="path to collection.anki2 (default: desktop 'User 1' profile)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="show the current code without modifying the collection",
    )
    args = ap.parse_args()
    return clear(args.path, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
