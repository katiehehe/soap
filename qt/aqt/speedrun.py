# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""SOA Exam P "Speedrun" desktop UI: the readiness dashboard and study map.

Hosts the SvelteKit ``readiness-dashboard`` page (``compute_readiness`` RPC,
honesty bundle / give-up state) and the ``study-map`` page (``get_mastery_state``
RPC, the three-layer topic tree with mastery-coloured edges).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import aqt
import aqt.main
from aqt import gui_hooks
from aqt.qt import QDialog, Qt, QTimer, QVBoxLayout
from aqt.utils import disable_help_button, restoreGeom, saveGeom, showInfo
from aqt.webview import AnkiWebView, AnkiWebViewKind

if TYPE_CHECKING:
    from anki.cards import Card
    from anki.collection import Collection


class ReadinessDialog(QDialog):
    def __init__(self, mw: aqt.main.AnkiQt) -> None:
        QDialog.__init__(self, mw, Qt.WindowType.Window)
        mw.garbage_collect_on_dialog_finish(self)
        self.mw = mw
        self.name = "speedrunReadiness"
        self.setWindowTitle("Exam readiness (Speedrun)")
        disable_help_button(self)

        self.web = AnkiWebView(kind=AnkiWebViewKind.SPEEDRUN)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.web)
        self.setLayout(layout)

        restoreGeom(self, self.name, default_size=(720, 820))
        self.web.load_sveltekit_page("readiness-dashboard")
        self.show()
        self.activateWindow()

    def reject(self) -> None:
        if self.web:
            self.web.cleanup()
            self.web = None  # type: ignore[assignment]
        saveGeom(self, self.name)
        QDialog.reject(self)


def show_readiness_dashboard(mw: aqt.main.AnkiQt) -> None:
    ReadinessDialog(mw)


class StudyMapDialog(QDialog):
    def __init__(self, mw: aqt.main.AnkiQt) -> None:
        QDialog.__init__(self, mw, Qt.WindowType.Window)
        mw.garbage_collect_on_dialog_finish(self)
        self.mw = mw
        self.name = "speedrunStudyMap"
        self.setWindowTitle("Study map (Speedrun)")
        disable_help_button(self)

        self.web = AnkiWebView(kind=AnkiWebViewKind.SPEEDRUN)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.web)
        self.setLayout(layout)

        restoreGeom(self, self.name, default_size=(820, 860))
        self.web.set_bridge_command(self._on_bridge_cmd, self)
        self.web.load_sveltekit_page("study-map")
        self.show()
        self.activateWindow()

    def _on_bridge_cmd(self, cmd: str) -> None:
        # The study map requests blocked practice on a subtopic's deck.
        prefix = "speedrun-study:"
        if cmd.startswith(prefix):
            self._study_subtopic(cmd[len(prefix) :])

    def _study_subtopic(self, tag: str) -> None:
        def start() -> None:
            # Close first, then open the subtopic's deck for blocked practice.
            self.close()
            open_subtopic_deck(self.mw, tag)

        # Defer so we don't tear down this webview from inside its own bridge
        # callback.
        QTimer.singleShot(0, start)

    def reject(self) -> None:
        if self.web:
            self.web.cleanup()
            self.web = None  # type: ignore[assignment]
        saveGeom(self, self.name)
        QDialog.reject(self)


def show_study_map(mw: aqt.main.AnkiQt) -> None:
    StudyMapDialog(mw)


def open_subtopic_deck(mw: aqt.main.AnkiQt, tag: str) -> bool:
    """Select a subtopic's deck and drop into review — i.e. blocked practice on
    just that subtopic. Returns False if the tag doesn't resolve to a deck."""
    from anki.speedrun import deck_name_for_subtopic_tag

    name = deck_name_for_subtopic_tag(tag)
    if not name:
        return False
    deck_id = mw.col.decks.id_for_name(name)
    if deck_id is None:
        return False
    mw.col.decks.select(deck_id)
    mw.col.startTimebox()
    mw.moveToState("review")
    return True


def recommended_subtopic_tag(col: Collection) -> str | None:
    """The highest-priority not-yet-cleared subtopic (importance weight x
    opportunity), or None when everything is mastered. Uses the engine's
    study-priority ranking, so it never fabricates a recommendation."""
    from anki import speedrun_pb2
    from anki.speedrun import expected_subtopic_tags, subtopic_weights, unit_weights

    state = col._backend.get_mastery_state(
        expected_subtopics=expected_subtopic_tags(),
        units=[speedrun_pb2.UnitWeight(unit_id=u, weight=w) for u, w in unit_weights()],
        subtopic_weights=[
            speedrun_pb2.SubtopicWeight(tag=t, weight=w) for t, w in subtopic_weights()
        ],
    )
    if not state.priorities:
        return None
    return state.priorities[0].tag


def study_recommended(mw: aqt.main.AnkiQt) -> None:
    """Open the recommended (highest-priority weak) subtopic for blocked
    practice — the good path in one click, whatever the user picked before."""
    tag = recommended_subtopic_tag(mw.col)
    if tag is None:
        showInfo("All subtopics are mastered — no recommendation right now.")
        return
    if not open_subtopic_deck(mw, tag):
        showInfo("Couldn't open the recommended subtopic's deck.")


# --- Reviewer mastery-tier banner ----------------------------------------
# Surfaces which tier the current card's subtopic is in during review
# (Blocked / Within-unit / Cross-unit), so the tier is visible rather than an
# invisible reorder. Registered once from main.py; read-only (no writes).

_TIER_LABELS: dict[int, tuple[str, str]] = {
    0: ("Blocked practice", "#e0a552"),  # build procedure in isolation
    1: ("Within-unit interleaving", "#6486bf"),  # train recognition
    2: ("Cross-unit review", "#57a37c"),  # spacing
}


def _tier_banner_enabled(col: Collection) -> bool:
    return bool(col.get_config("speedrunTierBanner", True))


def _current_subtopic_tag(card: Card) -> str | None:
    return next((t for t in card.note().tags if t.startswith("subtopic::")), None)


def _tier_for_tag(col: Collection, tag: str) -> tuple[str, str] | None:
    from anki.speedrun import expected_subtopic_tags, subtopic_name

    state = col._backend.get_mastery_state(
        expected_subtopics=expected_subtopic_tags(), units=[], subtopic_weights=[]
    )
    pool = next((s.pool for s in state.subtopics if s.tag == tag), None)
    if pool is None:
        return None
    label, color = _TIER_LABELS.get(pool, _TIER_LABELS[0])
    parts = tag.split("::")
    try:
        name = subtopic_name(parts[1], parts[2])
    except (IndexError, KeyError):
        name = tag
    return (f"{label} · {name}", color)


def _show_tier_banner(card: Card) -> None:
    mw = aqt.mw
    if mw is None or mw.col is None or mw.reviewer is None or mw.reviewer.web is None:
        return
    if not _tier_banner_enabled(mw.col):
        _clear_tier_banner()
        return
    tag = _current_subtopic_tag(card)
    info = _tier_for_tag(mw.col, tag) if tag else None
    if info is None:
        _clear_tier_banner()
        return
    text, color = info
    js = (
        "(function(){var b=document.getElementById('speedrun-tier');"
        "if(!b){b=document.createElement('div');b.id='speedrun-tier';"
        "b.style.cssText='position:fixed;top:0;left:0;right:0;z-index:2147483647;"
        "text-align:center;font:600 12px sans-serif;padding:4px 6px;"
        "pointer-events:none;';document.body.appendChild(b);}"
        f"b.textContent={json.dumps(text)};"
        f"b.style.color={json.dumps(color)};"
        f"b.style.background={json.dumps(color + '22')};"
        f"b.style.borderBottom='2px solid '+{json.dumps(color)};"
        "})();"
    )
    mw.reviewer.web.eval(js)


def _clear_tier_banner(*_args: object) -> None:
    mw = aqt.mw
    if mw is None or mw.reviewer is None or mw.reviewer.web is None:
        return
    mw.reviewer.web.eval(
        "var b=document.getElementById('speedrun-tier'); if(b){b.remove();}"
    )


def register_reviewer_banner() -> None:
    """Register the review-time mastery-tier banner hooks. Call once at startup."""
    gui_hooks.reviewer_did_show_question.append(_show_tier_banner)
    gui_hooks.reviewer_did_show_answer.append(_show_tier_banner)
    gui_hooks.reviewer_will_end.append(_clear_tier_banner)
