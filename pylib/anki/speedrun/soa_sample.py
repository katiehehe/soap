# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Held-out exam-style item corpus for the SOA Exam P Speedrun fork.

This corpus is the SINGLE held-out set behind three things:

- the AI subtopic-classifier gold set (``tools/speedrun/evals/classify_eval.py``),
- the performance model's disguised exam-style questions
  (``pylib/anki/speedrun/performance.py`` via the persona), and
- the practice-test item bank (``pylib/anki/speedrun/practice_test.py``).

Honesty / anti-leakage (rubric AUTOMATIC-FAIL if broken): every item here is
HELD OUT. It must never enter AI training, a retrieval index, or a few-shot
prompt. The leakage scan (``tools/speedrun/leakage_scan.py`` /
``evalsplit.find_leaks``) runs over these against any AI input.

Sourcing: the OWNER chose the official public "SOA Exam P Sample Questions" as
the real held-out set. Those items are copyrighted by the SOA, so they are NOT
committed to this AGPL repo. Instead:

- Drop the extracted items into ``data/soa_sample_p/items.json`` (gitignored);
  this loader prefers that file when present and records its provenance.
- Otherwise it falls back to ``sample_items.json`` next to this module: ORIGINAL,
  no-copyright, clearly-labelled exam-style items, so the whole pipeline, tests,
  and CI run with zero setup. See ``data/soa_sample_p/README.md``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

# Committed, original, no-copyright fallback corpus (ships with the repo).
_FALLBACK_PATH = Path(__file__).parent / "sample_items.json"

# Preferred real corpus: the official SOA sample questions, dropped in locally
# and kept out of version control (see data/soa_sample_p/README.md).
_REAL_DATA_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "soa_sample_p" / "items.json"
)

# Optional hand-authored LaTeX cleanups, keyed by item id, merged over the
# extracted corpus at load time. The PDF extraction mangles math (lost
# exponents/fractions/piecewise), so these restore clean \( \)/\[ \] LaTeX that
# MathJax renders. Kept SEPARATE from items.json so the extraction pipeline
# (regen.py) stays reproducible, and gitignored (derived from the copyrighted
# SOA questions). Never AI-generated — hand-authored, so no held-out leakage.
_LATEX_OVERRIDES_PATH = _REAL_DATA_PATH.parent / "latex_overrides.json"


@dataclass(frozen=True)
class SampleItem:
    """One held-out, exam-style item.

    ``source`` names where the item came from (e.g. ``"original-speedrun"`` or
    ``"soa-sample-2026"``) so every downstream use can trace it — required by the
    AI-traceability rule.
    """

    id: str
    question: str
    subtopic: str
    difficulty: str
    answer: str = ""
    source: str = ""

    @property
    def unit_id(self) -> str:
        parts = self.subtopic.split("::")
        return parts[1] if len(parts) == 3 else ""


@dataclass(frozen=True)
class SampleCorpus:
    items: list[SampleItem]
    source: str
    is_real_soa: bool
    path: str


def _parse(data: dict[str, Any], default_source: str, path: Path) -> list[SampleItem]:
    src = str(data.get("source", default_source))
    out: list[SampleItem] = []
    for raw in data.get("items", []):
        out.append(
            SampleItem(
                id=str(raw["id"]),
                question=str(raw["question"]),
                subtopic=str(raw["subtopic"]),
                difficulty=str(raw.get("difficulty", "medium")),
                answer=str(raw.get("answer", "")),
                source=str(raw.get("source", src)),
            )
        )
    if not out:
        raise ValueError(f"no items found in {path}")
    return out


def _apply_latex_overrides(items: list[SampleItem]) -> list[SampleItem]:
    """Merge hand-authored LaTeX cleanups (``latex_overrides.json``) over the
    extracted items, by id. Each override may set a clean ``question`` (and
    optionally ``answer``). Missing file / unknown ids are left untouched, so
    this is safe on any corpus (the ids only match the real SOA set)."""
    if not _LATEX_OVERRIDES_PATH.exists():
        return items
    try:
        with open(_LATEX_OVERRIDES_PATH, encoding="utf8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return items
    by_id = raw.get("items", raw)
    if not isinstance(by_id, dict):
        return items
    out: list[SampleItem] = []
    for it in items:
        ov = by_id.get(it.id)
        if isinstance(ov, dict):
            out.append(
                replace(
                    it,
                    question=str(ov.get("question", it.question)),
                    answer=str(ov.get("answer", it.answer)),
                )
            )
        else:
            out.append(it)
    return out


def load_corpus(path: str | None = None) -> SampleCorpus:
    """Load the held-out corpus.

    Preference order: an explicit ``path`` -> the real SOA data file (if the
    owner dropped it in) -> the committed original fallback. The returned
    ``is_real_soa`` flag lets callers label results honestly ("original
    fallback" vs "official SOA sample"). Hand-authored LaTeX cleanups are merged
    in (see ``_apply_latex_overrides``) so mangled math renders as clean LaTeX.
    """
    if path is not None:
        p = Path(path)
        with open(p, encoding="utf8") as f:
            items = _apply_latex_overrides(_parse(json.load(f), "external", p))
        return SampleCorpus(items, "external", False, str(p))
    if _REAL_DATA_PATH.exists():
        with open(_REAL_DATA_PATH, encoding="utf8") as f:
            items = _apply_latex_overrides(
                _parse(json.load(f), "soa-sample", _REAL_DATA_PATH)
            )
        return SampleCorpus(items, items[0].source, True, str(_REAL_DATA_PATH))
    with open(_FALLBACK_PATH, encoding="utf8") as f:
        items = _apply_latex_overrides(
            _parse(json.load(f), "original-speedrun", _FALLBACK_PATH)
        )
    return SampleCorpus(items, items[0].source, False, str(_FALLBACK_PATH))


def load_sample_items(path: str | None = None) -> list[SampleItem]:
    """Just the held-out items (see ``load_corpus`` for provenance)."""
    return load_corpus(path).items


def gold_items(path: str | None = None) -> list[dict[str, str]]:
    """The classifier gold set: ``{question, subtopic}`` pairs from the corpus.

    Kept in the same shape the keyword-baseline eval already consumes, so the
    held-out corpus is the one source of truth for the gold set.
    """
    return [
        {"question": it.question, "subtopic": it.subtopic}
        for it in load_sample_items(path)
    ]
