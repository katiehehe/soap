#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Open the synthetic demo persona in the desktop app — no manual studying.

    make demo

The demo persona (`out/demo-persona.anki2`, built by `make seed-persona` if
missing) already has 200+ graded reviews, FSRS memory state, and graded practice
tests, so the app opens straight into a FULLY POPULATED state: three signals each
with a range (Memory / Performance / Readiness), a colour-filled concept map,
today's tiered plan, and the exam-pace card — without grading a single card.

It uses a throwaway ANKI_BASE (`out/demo-base`) and its own "Demo" profile, so
your real Anki collection is never touched. Re-run any time; the collection is
refreshed from the latest persona on each launch.
"""

from __future__ import annotations

import os
import pickle
import random
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PERSONA = REPO / "out" / "demo-persona.anki2"
BASE = REPO / "out" / "demo-base"
PROFILE = "Demo"


def _seed_prefs(base: Path) -> None:
    """Seed prefs21.db so Anki skips the language picker + profile chooser and
    opens the Demo profile straight away (mirrors qt/tests/launch_anki_for_e2e)."""
    meta = {
        "ver": 0,
        "updates": False,
        "created": int(time.time()),
        "id": random.randrange(0, 2**63),
        "lastMsg": 0,
        "suppressUpdate": True,
        "firstRun": False,
        "defaultLang": "en_US",
        "check_for_updates": False,
    }
    profile = {
        "mainWindowGeom": None,
        "mainWindowState": None,
        "numBackups": 0,
        "lastOptimize": int(time.time()),
        "searchHistory": [],
        "syncKey": None,
        "syncMedia": False,
        "autoSync": False,
        "allowHTML": False,
        "importMode": 1,
        "lastColour": "#00f",
        "stripHTML": True,
        "deleteMedia": False,
    }
    db_path = base / "prefs21.db"
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "create table profiles (name text primary key collate nocase, data blob not null)"
    )
    conn.execute(
        "insert into profiles values ('_global', ?)", (pickle.dumps(meta, protocol=4),)
    )
    conn.execute(
        "insert into profiles values (?, ?)",
        (PROFILE, pickle.dumps(profile, protocol=4)),
    )
    conn.commit()
    conn.close()


def main() -> int:
    if not PERSONA.exists():
        print("Demo persona missing; building it (make seed-persona)...")
        subprocess.run(
            [sys.executable, str(REPO / "tools" / "speedrun" / "seed_persona.py")],
            check=True,
            cwd=str(REPO),
        )
    (BASE / PROFILE).mkdir(parents=True, exist_ok=True)
    _seed_prefs(BASE)
    # Fresh copy of the persona each launch, so demo edits never accumulate and
    # the collection always reflects the latest `make seed-persona`.
    shutil.copy(PERSONA, BASE / PROFILE / "collection.anki2")

    print("=" * 70)
    print("Opening the SYNTHETIC DEMO PERSONA in a throwaway profile.")
    print(f"  base    : {BASE}")
    print("  profile : Demo   (your real Anki collection is NOT touched)")
    print("Everything is pre-populated: open Tools -> Exam readiness (Speedrun)")
    print("and Tools -> Study map (Speedrun) to see all three signals + the map.")
    print("=" * 70)

    if os.environ.get("SKIP_RUN"):
        print("SKIP_RUN set: setup only, not launching the GUI.")
        return 0

    os.environ["ANKI_BASE"] = str(BASE)
    sys.path[:0] = ["pylib", "qt", "out/pylib", "out/qt"]
    os.chdir(REPO)
    sys.argv = ["anki", "-b", str(BASE), "-p", PROFILE]
    import aqt

    aqt.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
