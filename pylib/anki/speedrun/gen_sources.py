# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Loader for the named AI-generation SOURCES (``gen_sources.json``).

Every AI-generated card/problem must be grounded in, and cite, one of these
sources (the AI-traceability rule). These are ORIGINAL, no-copyright statements
of standard probability facts, one per syllabus subtopic; they are AI INPUTS, so
they are scanned against the held-out corpus by the leakage gate
(``tools/speedrun/leakage_scan_text.py``).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_PATH = Path(__file__).parent / "gen_sources.json"


@lru_cache(maxsize=1)
def load_sources() -> list[dict[str, Any]]:
    """All named source records (id, name, subtopic, passage, key_terms)."""
    return json.loads(_PATH.read_text(encoding="utf-8"))["sources"]


def source_for_subtopic(subtopic_tag: str) -> dict[str, Any] | None:
    """The named source for a subtopic tag, or None if none is defined."""
    for source in load_sources():
        if source.get("subtopic") == subtopic_tag:
            return source
    return None
