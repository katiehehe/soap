# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""SOA Exam P "Speedrun" desktop UI: the readiness dashboard and study map.

Hosts the SvelteKit ``readiness-dashboard`` page (``compute_readiness`` RPC,
honesty bundle / give-up state) and the ``study-map`` page (``get_mastery_state``
RPC, the three-layer topic tree with mastery-coloured edges).
"""

from __future__ import annotations

import json
from collections.abc import Callable
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
    from anki.decks import DeckId


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
        # The study map requests a tier of practice. Defer so we don't tear down
        # this webview from inside its own bridge callback.
        if cmd.startswith("speedrun-study-deck:"):
            # Today's-plan row: open a specific deck by id (robust to display
            # names differing from deck names).
            raw = cmd[len("speedrun-study-deck:") :]
            try:
                did = int(raw)
            except ValueError:
                return
            self._deferred(lambda: open_deck_by_id(self.mw, did))
        elif cmd.startswith("speedrun-study-unit:"):
            unit_id = cmd[len("speedrun-study-unit:") :]
            self._deferred(lambda: open_unit_deck(self.mw, unit_id))
        elif cmd == "speedrun-study-all":
            self._deferred(lambda: open_all_deck(self.mw))
        elif cmd.startswith("speedrun-study:"):
            tag = cmd[len("speedrun-study:") :]
            self._deferred(lambda: open_subtopic_deck(self.mw, tag))
        elif cmd.startswith("speedrun-set-exam-date:"):
            iso = cmd[len("speedrun-set-exam-date:") :]
            self._apply_and_reload(lambda: set_exam_date_cmd(self.mw, iso))
        elif cmd == "speedrun-clear-exam-date":
            self._apply_and_reload(lambda: clear_exam_date_cmd(self.mw))
        elif cmd.startswith("speedrun-set-new-per-day:"):
            n = _parse_positive_int(cmd[len("speedrun-set-new-per-day:") :])
            if n is not None:
                self._apply_and_reload(lambda: set_new_per_day(self.mw, n))
        elif cmd.startswith("speedrun-extend-new:"):
            n = _parse_positive_int(cmd[len("speedrun-extend-new:") :])
            if n is not None:
                self._deferred(lambda: extend_new_and_study(self.mw, n))

    def _deferred(self, open_fn: Callable[[], bool]) -> None:
        def start() -> None:
            self.close()
            open_fn()

        QTimer.singleShot(0, start)

    def _apply_and_reload(self, action: Callable[[], object]) -> None:
        # Mutate config/limits, then reload the page so the pace card re-reads it.
        # Deferred so we don't reload the webview from inside its own callback.
        def run() -> None:
            action()
            self.web.load_sveltekit_page("study-map")

        QTimer.singleShot(0, run)

    def reject(self) -> None:
        if self.web:
            self.web.cleanup()
            self.web = None  # type: ignore[assignment]
        saveGeom(self, self.name)
        QDialog.reject(self)


def show_study_map(mw: aqt.main.AnkiQt) -> None:
    StudyMapDialog(mw)


def _start_review(mw: aqt.main.AnkiQt, deck_id: DeckId) -> None:
    mw.col.decks.select(deck_id)
    mw.col.startTimebox()
    mw.moveToState("review")


def _open_named_deck(mw: aqt.main.AnkiQt, name: str | None) -> bool:
    if not name:
        return False
    deck_id = mw.col.decks.id_for_name(name)
    if deck_id is None:
        return False
    _start_review(mw, deck_id)
    return True


def open_subtopic_deck(mw: aqt.main.AnkiQt, tag: str) -> bool:
    """Blocked practice: study just this subtopic's deck."""
    from anki.speedrun import deck_name_for_subtopic_tag

    return _open_named_deck(mw, deck_name_for_subtopic_tag(tag))


def open_unit_deck(mw: aqt.main.AnkiQt, unit_id: str) -> bool:
    """Within-unit interleaving: study a whole unit's deck. The scheduler serves
    its still-blocked subtopics first, then interleaves the cleared ones."""
    from anki.speedrun import unit_deck_name

    return _open_named_deck(mw, unit_deck_name(unit_id))


def open_all_deck(mw: aqt.main.AnkiQt) -> bool:
    """Cross-unit review: study the whole exam deck."""
    from anki.speedrun.seed import ROOT_DECK

    return _open_named_deck(mw, ROOT_DECK)


def open_deck_by_id(mw: aqt.main.AnkiQt, deck_id: int) -> bool:
    """Open a specific deck (by id) for review, for a Today's-plan row. Uses the
    id the engine returned, so it's robust to display names differing from deck
    names. Returns False if the deck no longer exists."""
    from anki.decks import DeckId

    if mw.col.decks.get(DeckId(deck_id), default=False) is None:
        return False
    _start_review(mw, DeckId(deck_id))
    return True


def _parse_positive_int(raw: str) -> int | None:
    try:
        n = int(raw)
    except ValueError:
        return None
    return n if n >= 1 else None


def set_exam_date_cmd(mw: aqt.main.AnkiQt, iso: str) -> None:
    """Store the target exam date (ISO YYYY-MM-DD) so the pace card can show
    whether the student is on track. Only affects the pace read-out."""
    from anki.speedrun import set_exam_date

    set_exam_date(mw.col, iso)


def clear_exam_date_cmd(mw: aqt.main.AnkiQt) -> None:
    from anki.speedrun import clear_exam_date

    clear_exam_date(mw.col)


def set_new_per_day(mw: aqt.main.AnkiQt, n: int) -> None:
    """Set the exam deck's steady new-cards/day limit (the 'get on track' lever).
    Note: if the exam deck shares the default preset, this changes that preset."""
    from anki.speedrun.seed import ROOT_DECK

    did = mw.col.decks.id_for_name(ROOT_DECK)
    if did is None:
        return
    conf = mw.col.decks.config_dict_for_deck_id(did)
    conf["new"]["perDay"] = int(n)
    mw.col.decks.update_config(conf)


def extend_new_and_study(mw: aqt.main.AnkiQt, n: int) -> bool:
    """'Study more today': raise TODAY's new-card allowance on the exam deck by
    n and open it for review, so a heavy study day isn't blocked by the daily
    quota. Today-only (uses extend_limits); the steady limit is untouched."""
    from anki.speedrun.seed import ROOT_DECK

    did = mw.col.decks.id_for_name(ROOT_DECK)
    if did is None:
        return False
    mw.col.decks.select(did)
    mw.col.sched.extend_limits(n, 0)
    _start_review(mw, did)
    return True


def study_recommended(mw: aqt.main.AnkiQt) -> None:
    """Open the engine's tier-aware recommended next practice in one click:
    blocked practice on the weakest subtopic, within-unit interleaving of a unit
    that's underway, or cross-unit review once everything is cleared. Never
    fabricated — it only reflects the measured gate state."""
    from anki import speedrun_pb2
    from anki.speedrun import expected_subtopic_tags, subtopic_weights, unit_weights

    state = mw.col._backend.get_mastery_state(
        expected_subtopics=expected_subtopic_tags(),
        units=[speedrun_pb2.UnitWeight(unit_id=u, weight=w) for u, w in unit_weights()],
        subtopic_weights=[
            speedrun_pb2.SubtopicWeight(tag=t, weight=w) for t, w in subtopic_weights()
        ],
    )
    rec = state.recommendation
    # StudyMode: BLOCKED=0, WITHIN_UNIT=1, CROSS_UNIT=2, ALL_MASTERED=3.
    if rec.mode == 0 and rec.subtopic_tag:
        ok = open_subtopic_deck(mw, rec.subtopic_tag)
    elif rec.mode == 1 and rec.unit_id:
        ok = open_unit_deck(mw, rec.unit_id)
    else:
        ok = open_all_deck(mw)
    if not ok:
        showInfo("Couldn't open the recommended deck.")


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
