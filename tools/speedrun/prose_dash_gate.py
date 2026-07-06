#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Prose dash gate: the single source of truth for banned-dash detection.

Three layers reuse this one detector so detection never drifts:
  1. a Cursor `postToolUse` hook (`.cursor/hooks/prose-dash-hook.py`) that runs
     it on files the agent just edited and feeds any hit back into the loop,
  2. a `pre-commit` stage hook (`.pre-commit-config.yaml`) that fails the commit,
  3. the always-applied rule `.cursor/rules/prose-dashes.mdc` (prevention).

Banned code points (never legitimate as prose in this codebase):
  U+2013 EN DASH, U+2014 EM DASH, U+2015 HORIZONTAL BAR.
Conditionally banned:
  U+2212 MINUS SIGN. This is real math in an actuarial exam app (a parser in
  `pylib/anki/speedrun/practice_test.py` matches it on purpose), so a line is
  exempt when it carries the inline allow-marker token ``dash-ok``.

This file itself must stay clean, so every banned character below is written as
a ``\\uXXXX`` escape, never as the literal glyph.

Usage:
    # check explicit files (what pre-commit passes):
    python3 tools/speedrun/prose_dash_gate.py path/to/file.py ...
    # check everything currently staged:
    python3 tools/speedrun/prose_dash_gate.py --staged
    # check given files ignoring the owned-area allowlist (still skips the
    # denylist); used to self-test files outside the owned tree:
    python3 tools/speedrun/prose_dash_gate.py --force .cursor/rules/prose-dashes.mdc

Exit status is non-zero if any hit is found, so it works as a commit gate.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

# Always-banned dashes -> human label. Written as escapes so this file is clean.
BANNED = {
    "\u2013": "EN DASH (U+2013)",
    "\u2014": "EM DASH (U+2014)",
    "\u2015": "HORIZONTAL BAR (U+2015)",
}
# Conditionally banned: legitimate only on a line carrying the allow-marker.
MINUS = "\u2212"
MINUS_LABEL = "MINUS SIGN (U+2212)"
ALLOW_MARKER = "dash-ok"

# Vendored / generated / upstream trees we never own. Skipped entirely, and a
# `--force` self-test still honours these (we never want to scan generated code).
DENY_DIRS = {
    ".git",
    "node_modules",
    "target",
    "out",
    "ftl",
    "docs-site",
    "__pycache__",
}
DENY_SUFFIXES = ("licenses.json",)

# Areas this fork owns and should keep clean. A file is checked only when it
# lives here (or is a root-level Markdown doc); everything else is upstream Anki
# and left alone unless `--force` is passed.
OWNED_PREFIXES = (
    "pylib/anki/speedrun/",
    "pylib/tests/",
    "rslib/src/speedrun/",
    "ts/routes/",
    "ts/tests/",
    "tools/speedrun/",
    "docs/",
)
OWNED_FILES = {"qt/aqt/speedrun.py"}


def repo_root() -> str:
    """Repo root, derived from this file's location (tools/speedrun/<file>)."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _rel(path: str) -> str:
    """Repo-relative POSIX path (may start with ``..`` for files outside root)."""
    rel = os.path.relpath(os.path.abspath(path), repo_root())
    return rel.replace(os.sep, "/")


def is_denied(rel: str) -> bool:
    segments = rel.split("/")
    if any(seg in DENY_DIRS for seg in segments):
        return True
    return rel.endswith(DENY_SUFFIXES)


def is_owned(rel: str) -> bool:
    if rel in OWNED_FILES:
        return True
    if rel.startswith(OWNED_PREFIXES):
        return True
    # Root-level Markdown docs (README.md, PRD.md, SPEC_CHECKLIST.md, ...).
    return "/" not in rel and rel.lower().endswith(".md")


def should_check(path: str, force: bool = False) -> bool:
    """Whether a path is in scope. Denylist always wins; `force` bypasses only
    the owned-area allowlist."""
    rel = _rel(path)
    if is_denied(rel):
        return False
    if force:
        return True
    return is_owned(rel)


def scan_file(path: str) -> list[tuple[int, int, str]]:
    """Return (line, column, label) for every banned-dash hit in one file.

    A U+2212 occurrence is a hit only when the line lacks the allow-marker.
    Unreadable or non-UTF-8 files are skipped (no hits)."""
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.readlines()
    except (OSError, UnicodeDecodeError):
        return []

    hits: list[tuple[int, int, str]] = []
    for lineno, line in enumerate(lines, start=1):
        exempt = ALLOW_MARKER in line
        for col, char in enumerate(line, start=1):
            label = BANNED.get(char)
            if label is not None:
                hits.append((lineno, col, label))
            elif char == MINUS and not exempt:
                hits.append((lineno, col, MINUS_LABEL))
    return hits


def _staged_files() -> list[str]:
    """Repo-relative paths of files staged for commit (added/copied/modified/
    renamed)."""
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
            cwd=repo_root(),
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return []
    return [name for name in out.split("\0") if name]


def _unique(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            ordered.append(path)
    return ordered


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", help="files to check")
    parser.add_argument(
        "--staged", action="store_true", help="also check files staged for commit"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="check the given files even outside owned areas (still skips the denylist)",
    )
    args = parser.parse_args()

    paths = list(args.files)
    if args.staged:
        paths += _staged_files()

    hits: list[tuple[str, int, int, str]] = []
    for path in _unique(paths):
        if not should_check(path, force=args.force):
            continue
        for lineno, col, label in scan_file(path):
            hits.append((path, lineno, col, label))

    for path, lineno, col, label in hits:
        print(f"{path}:{lineno}:{col}: {label}")

    if hits:
        print(
            f"\n{len(hits)} banned-dash hit(s). Use a hyphen '-' for ranges, "
            "commas or parentheses for asides, a colon for a clause break. For "
            f"intentional math (U+2212), append a '{ALLOW_MARKER}' comment to the "
            "line. See .cursor/rules/prose-dashes.mdc and the prose-cleanup skill.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
