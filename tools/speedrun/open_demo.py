#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Open a synthetic demo persona in the desktop app, no manual studying needed.

    make demo               # intermediate: a real readiness range (default)
    make demo-new           # barely studied: readiness honestly abstains
    make demo-experienced   # well-prepared: a high, tight readiness range

Each scenario's collection (built by ``seed_persona.py`` if missing) already has
its synthetic study history, so the app opens straight into a populated state:
the three signals (Memory / Performance / Readiness), a colour-filled concept
map, today's tiered plan, and the exam-pace card, all without grading a card. The
"new" scenario opens into the honest ABSTAIN state (the give-up rule), which is
the point of that demo.

Each scenario uses its own throwaway ANKI_BASE (e.g. `out/demo-base-new`) and a
"Demo" profile, so your real Anki collection is never touched and scenarios never
clobber each other. Re-run any time; the collection is refreshed from the latest
persona on each launch.
"""

from __future__ import annotations

import argparse
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
PROFILE = "Demo"


def scenario_paths(scenario: str) -> tuple[Path, Path]:
    """The (persona collection, ANKI_BASE) for a scenario. Mirrors the per-scenario
    filenames written by ``seed_persona.py``; ``intermediate`` keeps the canonical
    ``out/demo-persona.anki2`` and ``out/demo-base`` other tooling depends on."""
    if scenario == "intermediate":
        return REPO / "out" / "demo-persona.anki2", REPO / "out" / "demo-base"
    return (
        REPO / "out" / f"demo-persona-{scenario}.anki2",
        REPO / "out" / f"demo-base-{scenario}",
    )


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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=("new", "intermediate", "experienced"),
        default="intermediate",
        help="which mock user to open (default: intermediate)",
    )
    args = parser.parse_args()
    persona, base = scenario_paths(args.scenario)

    if not persona.exists():
        print(f"Demo persona missing; building the {args.scenario!r} scenario...")
        subprocess.run(
            [
                sys.executable,
                str(REPO / "tools" / "speedrun" / "seed_persona.py"),
                "--scenario",
                args.scenario,
            ],
            check=True,
            cwd=str(REPO),
        )
    (base / PROFILE).mkdir(parents=True, exist_ok=True)
    _seed_prefs(base)
    # Fresh copy of the persona each launch, so demo edits never accumulate and
    # the collection always reflects the latest seed.
    shutil.copy(persona, base / PROFILE / "collection.anki2")

    print("=" * 70)
    print(f"Opening the {args.scenario!r} SYNTHETIC DEMO PERSONA in a throwaway profile.")
    print(f"  base    : {base}")
    print("  profile : Demo   (your real Anki collection is NOT touched)")
    print("Everything is pre-populated: open Tools -> Exam readiness (Speedrun)")
    print("and Tools -> Study map (Speedrun) to see all three signals + the map.")
    print("=" * 70)

    if os.environ.get("SKIP_RUN"):
        print("SKIP_RUN set: setup only, not launching the GUI.")
        return 0

    os.environ["ANKI_BASE"] = str(base)
    sys.path[:0] = ["pylib", "qt", "out/pylib", "out/qt"]
    os.chdir(REPO)
    sys.argv = ["anki", "-b", str(base), "-p", PROFILE]
    import aqt

    aqt.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
