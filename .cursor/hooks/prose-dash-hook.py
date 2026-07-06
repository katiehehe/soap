#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Cursor postToolUse hook: catch banned dashes the agent just wrote.

Why postToolUse and not afterFileEdit: afterFileEdit is notification-only (it
cannot return anything the agent reads). postToolUse can return
`additional_context`, which Cursor injects into the conversation after the tool
result, so the agent sees the problem and fixes it in the same loop.

This is a thin wrapper. All detection lives in
`tools/speedrun/prose_dash_gate.py` (the single source of truth), so the hook,
the pre-commit gate, and any manual scan agree.

Behavior: read the postToolUse JSON on stdin, and for file-editing tools only,
run the detector on the edited file. On a hit, print
`{"additional_context": ...}`; otherwise print `{}`. Always exit 0 and fail
open (never disrupt the agent loop over a hook error).
"""

from __future__ import annotations

import json
import os
import sys

# Substrings (case-insensitive) that mark a file-editing tool. Keeps the hook
# from doing any work after reads, searches, or shell calls.
_EDIT_TOOL_HINTS = ("write", "edit", "replace", "create", "patch", "notebook")
# tool_input keys that may carry the edited file path, in priority order.
_PATH_KEYS = (
    "path",
    "file_path",
    "target_file",
    "target_notebook",
    "filePath",
    "absolute_path",
    "notebook_path",
)


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj))


def _is_edit_tool(tool_name: str) -> bool:
    lowered = tool_name.lower()
    return any(hint in lowered for hint in _EDIT_TOOL_HINTS)


def _extract_path(tool_input: object) -> str | None:
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except (ValueError, TypeError):
            return None
    if not isinstance(tool_input, dict):
        return None
    for key in _PATH_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _load_detector():
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    tools_dir = os.path.join(repo, "tools", "speedrun")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    import prose_dash_gate  # noqa: E402

    return prose_dash_gate


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (ValueError, TypeError):
        _emit({})
        return 0

    tool_name = str(payload.get("tool_name") or "")
    if not _is_edit_tool(tool_name):
        _emit({})
        return 0

    path = _extract_path(payload.get("tool_input"))
    if not path:
        _emit({})
        return 0

    if not os.path.isabs(path):
        base = payload.get("cwd") or os.environ.get("CURSOR_PROJECT_DIR") or os.getcwd()
        path = os.path.join(base, path)

    try:
        gate = _load_detector()
        if not gate.should_check(path):
            _emit({})
            return 0
        hits = gate.scan_file(path)
    except Exception:
        _emit({})
        return 0

    if not hits:
        _emit({})
        return 0

    listed = "\n".join(
        f"  line {line}, col {col}: {label}" for line, col, label in hits
    )
    message = (
        f"Prose dash gate: '{os.path.relpath(path, gate.repo_root())}' now contains "
        f"{len(hits)} banned-dash character(s) you must fix before continuing:\n"
        f"{listed}\n"
        "Replace with a hyphen '-' for ranges, a comma or parentheses for an "
        "aside, or a colon for a clause break. If a U+2212 is intentional math, "
        "append a 'dash-ok' comment to that line. See "
        ".cursor/rules/prose-dashes.mdc and the prose-cleanup skill."
    )
    _emit({"additional_context": message})
    return 0


if __name__ == "__main__":
    sys.exit(main())
