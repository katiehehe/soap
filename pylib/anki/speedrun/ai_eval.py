# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Committed, re-runnable AI-eval ARTIFACT builder (Friday AI proof).

The three AI evals (``classify_eval`` / ``generate_eval`` / ``problem_eval``)
each expose a ``collect_results()`` that returns a JSON-serialisable per-eval
record. This module wraps those records into one machine-readable artifact and
writes it to a committed path, so the "AI beats a simpler baseline" claim lives
as a reproducible FILE, not free-floating prose.

Honesty contract (hard rule, see .cursor/rules/ai-traceability.mdc):

- **Baseline / offline cells are reproducible without a key** and are always
  filled in.
- **AI cells are populated ONLY when the eval ran against a real provider**
  (``OPENAI_API_KEY`` set). With no key the AI cell is ``null`` and the verdict
  is ``"pending"``, never a fabricated or hardcoded number.
- The top-level ``ai_ran`` flag + per-eval ``ai_ran`` let a reader tell at a
  glance whether the AI side is real or pending, and ``git_sha`` +
  ``generated_at_*`` date the run.

The heavy per-eval computation stays in the eval scripts (``tools/speedrun/``);
this module is pure wrapper + I/O so it can be unit-tested with no key/network.
"""

from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Bump when the artifact shape changes so readers can detect a mismatch.
SCHEMA_VERSION = 1


def repo_root() -> Path:
    """Repo root, from this file at ``pylib/anki/speedrun/ai_eval.py``."""
    return Path(__file__).resolve().parents[3]


# The committed artifact path (relative to the repo root).
DEFAULT_ARTIFACT_PATH = (
    repo_root() / "tools" / "speedrun" / "evals" / "results" / "ai_eval.json"
)

_NOTE = (
    "Baseline/offline cells are reproducible with no key and are always filled. "
    "AI cells are populated only when the eval ran with OPENAI_API_KEY; when "
    "absent they are null and the verdict is 'pending', never fabricated. "
    "Regenerate with `make ai-report` (add OPENAI_API_KEY to populate AI cells)."
)


def read_git_sha(repo: str | Path | None = None) -> str | None:
    """Short HEAD SHA for provenance, or None if git is unavailable."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(repo or repo_root()),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception:  # noqa: BLE001 (provenance is best-effort, never fatal)
        return None
    sha = out.stdout.strip()
    return sha or None


def _any_subsample(evals: dict[str, dict[str, Any]]) -> bool:
    """True iff any eval's populated AI cell is a subsample (a keyed smoke run)."""
    for e in evals.values():
        ai = e.get("ai")
        if isinstance(ai, dict) and ai.get("is_subsample"):
            return True
    return False


def build_report(
    evals: dict[str, dict[str, Any]],
    *,
    ai_provider: str | None = None,
    ai_model: str | None = None,
    git_sha: str | None = None,
    generated_at: int | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    """Assemble the full artifact from per-eval records.

    ``evals`` maps an eval key (e.g. ``"classify"``) to its ``collect_results()``
    record. ``ai_ran`` and ``is_subsample`` are DERIVED from the per-eval cells,
    so the top-level flags can never disagree with them. Pure + deterministic
    given its inputs (pass ``generated_at`` to pin the timestamp in tests).
    """
    ts = int(time.time()) if generated_at is None else int(generated_at)
    ai_ran = any(bool(e.get("ai_ran")) for e in evals.values())
    is_subsample = _any_subsample(evals)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_unix": ts,
        "generated_at_utc": datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "git_sha": git_sha,
        "ai_ran": ai_ran,
        # A keyed run over a capped subsample (a smoke run), NOT the full held-out
        # set. When true, the AI cells are sampled and must not be read as the
        # full result: the per-eval AI cells carry sample_size/seed.
        "is_subsample": is_subsample if ai_ran else False,
        # Only name a provider/model when the AI side actually ran, so a pending
        # artifact never implies an AI result it does not have.
        "ai_provider": ai_provider if ai_ran else None,
        "ai_model": ai_model if ai_ran else None,
        "seed": seed if ai_ran else None,
        "note": _NOTE,
        "evals": evals,
    }


def write_report(report: dict[str, Any], path: str | Path | None = None) -> Path:
    """Write the artifact as pretty JSON (trailing newline), creating the dir."""
    p = Path(path) if path is not None else DEFAULT_ARTIFACT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return p
