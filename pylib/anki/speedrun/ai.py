# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""AI gateway for the SOA Exam P Speedrun fork (scaffolding for Friday).

Every model-backed feature must go through this module so they share ONE hard
off-switch. AI is OFF by default: with it off, readiness, the study map, and the
deck all work unchanged, and the Rust engine never depends on AI. Actual model
calls (the subtopic classifier, card generation) land here on Friday — see
``docs/ai-features-prd.md``. Today this only carries the flag and the contract,
so nothing here affects the running app.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anki.collection import Collection

# Collection-config key. Absent/false => AI disabled (the default).
AI_ENABLED_KEY = "speedrunAiEnabled"


def ai_enabled(col: Collection) -> bool:
    """Whether AI features are on. Default False — the app must score with AI off."""
    return bool(col.get_config(AI_ENABLED_KEY, False))


def set_ai_enabled(col: Collection, enabled: bool) -> None:
    """Toggle the AI off-switch (used by settings + the AI-off ablation build)."""
    col.set_config(AI_ENABLED_KEY, enabled)


class AiDisabledError(RuntimeError):
    """Raised when an AI feature is invoked while the off-switch is engaged."""


def require_ai(col: Collection) -> None:
    """Guard for AI entry points: refuse to run when AI is switched off.

    Every future AI function (classify_subtopic, generate_cards, ...) calls this
    first, so there is a single, testable enforcement point for "AI off".
    """
    if not ai_enabled(col):
        raise AiDisabledError(
            "AI is disabled. Enable it in settings to use this feature; "
            "the app still produces all scores with AI off."
        )
