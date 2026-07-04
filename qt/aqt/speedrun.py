# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""SOA Exam P "Speedrun" desktop UI: the readiness dashboard and study map.

Hosts the SvelteKit ``readiness-dashboard`` page (``compute_readiness`` RPC,
honesty bundle / give-up state) and the ``study-map`` page (``get_mastery_state``
RPC, the three-layer topic tree with mastery-coloured edges).
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aqt
import aqt.main
from aqt import gui_hooks
from aqt.qt import QDialog, Qt, QTimer, QVBoxLayout
from aqt.utils import disable_help_button, restoreGeom, saveGeom, tooltip
from aqt.webview import AnkiWebView, AnkiWebViewKind, WebContent

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
        elif cmd.startswith("speedrun-practice-unit:"):
            unit_id = cmd[len("speedrun-practice-unit:") :]
            self._deferred(lambda: practice_unit(self.mw, unit_id))
        elif cmd == "speedrun-practice-all":
            self._deferred(lambda: practice_all(self.mw))
        elif cmd.startswith("speedrun-practice:"):
            tag = cmd[len("speedrun-practice:") :]
            self._deferred(lambda: practice_subtopic(self.mw, tag))
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
        elif cmd.startswith("speedrun-set-guided:"):
            raw = cmd[len("speedrun-set-guided:") :]
            # Write config only; the page re-reads mastery state itself.
            self._apply_only(lambda: set_guided_cmd(self.mw, raw))
        elif cmd.startswith("speedrun-set-scheduler:"):
            raw = cmd[len("speedrun-set-scheduler:") :]
            self._apply_only(lambda: set_scheduler_cmd(self.mw, raw))
        elif cmd.startswith("speedrun-unlock:"):
            tag = cmd[len("speedrun-unlock:") :]
            self._apply_only(lambda: unlock_subtopic_cmd(self.mw, tag))

    def _deferred(self, open_fn: Callable[[], bool]) -> None:
        def start() -> None:
            self.close()
            open_fn()

        QTimer.singleShot(0, start)

    def _apply_only(self, action: Callable[[], object]) -> None:
        # Mutate config without reloading/closing the page; the SvelteKit page
        # re-fetches mastery state after issuing the command, so the lock/toggle
        # updates in place. Deferred so we never mutate from inside the callback.
        QTimer.singleShot(0, action)

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
    # A study button must never bounce the user to the "Congratulations, finished"
    # screen: if the selected deck has nothing to study right now, say so quietly
    # and stay put. `_is_finished` is a read-only queue build (no writes, so undo /
    # integrity are unaffected); guarded with getattr so an older scheduler just
    # falls through to the normal path.
    is_finished = getattr(mw.col.sched, "_is_finished", None)
    if callable(is_finished) and is_finished():
        leaf = mw.col.decks.name(deck_id).split("::")[-1]
        tooltip(
            f"Nothing to study in “{leaf}” right now — you're caught up.",
            parent=mw,
        )
        return
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


# One reusable no-reschedule filtered ("cram") deck for UNLIMITED free practice.
# It is re-pointed to whatever scope the user practices (a subtopic, a unit, or
# everything), so practice decks never pile up. Because reschedule is OFF,
# cramming any amount never touches FSRS scheduling or the daily new/review
# limits — it feeds the Performance side, not the Memory schedule.
PRACTICE_DECK = "SOA Exam P \u2014 Practice"


def _start_practice(mw: aqt.main.AnkiQt, search: str) -> bool:
    from anki.decks import DeckId, FilteredDeckConfig

    existing = mw.col.decks.id_for_name(PRACTICE_DECK)
    deck_id = DeckId(existing) if existing is not None else DeckId(0)
    deck = mw.col.sched.get_or_create_filtered_deck(deck_id=deck_id)
    deck.name = PRACTICE_DECK
    cfg = deck.config
    cfg.reschedule = False  # pure practice: never reschedule or hit daily limits
    del cfg.search_terms[:]
    term = cfg.search_terms.add()
    term.search = search
    term.limit = 9999
    term.order = FilteredDeckConfig.SearchTerm.Order.RANDOM  # good for practice
    out = mw.col.sched.add_or_update_filtered_deck(deck)
    _start_review(mw, DeckId(out.id))
    return True


def practice_subtopic(mw: aqt.main.AnkiQt, tag: str) -> bool:
    """Unlimited practice of one subtopic's cards (no-reschedule)."""
    from anki.speedrun import deck_name_for_subtopic_tag

    return _start_practice(mw, f'deck:"{deck_name_for_subtopic_tag(tag)}"')


def practice_unit(mw: aqt.main.AnkiQt, unit_id: str) -> bool:
    """Unlimited practice of a whole unit's cards (no-reschedule)."""
    from anki.speedrun import unit_deck_name

    return _start_practice(mw, f'deck:"{unit_deck_name(unit_id)}"')


def practice_all(mw: aqt.main.AnkiQt) -> bool:
    """Unlimited practice of the whole exam deck (no-reschedule)."""
    from anki.speedrun.seed import ROOT_DECK

    return _start_practice(mw, f'deck:"{ROOT_DECK}"')


# --- In-app practice tests (drive the Performance + Readiness signals) --------
# The exam-shaped test is assembled/graded/recorded in Python (practice_test.py);
# the webview calls these two commands and gets JSON back via the bridge callback.
# Every test is drawn from the PRE-BUILT bank (held-out corpus + templated /
# verified-AI pool) — never generated on the spot — so it starts instantly and
# stays exactly timed. Data only: assembling writes nothing; grading records REAL
# graded evidence that the readiness engine reads (still behind the give-up
# rule), weighted by how representative the test was. No score is faked.


def _test_params(raw: str) -> tuple[int, int, str, str]:
    """Parse "seed,size,scope[,source]"; scope is "all" | "unit:<id>" |
    "subtopic:<tag>". A legacy trailing source field is tolerated but ignored —
    every test now draws from the pre-built bank (no on-the-spot generation)."""
    parts = raw.split(",", 3)
    try:
        seed = int(parts[0])
    except (ValueError, IndexError):
        seed = 0
    try:
        size = int(parts[1])
    except (ValueError, IndexError):
        size = 10
    scope = parts[2] if len(parts) > 2 and parts[2] else "all"
    source = parts[3] if len(parts) > 3 and parts[3] else "official"
    return seed, max(1, min(size, 60)), scope, source


def _scope_items(items: list, scope: str) -> list:
    """Filter the held-out corpus to a scope: one subtopic, a unit, or all."""
    if scope.startswith("subtopic:"):
        tag = scope[len("subtopic:") :]
        return [it for it in items if it.subtopic == tag]
    if scope.startswith("unit:"):
        uid = scope[len("unit:") :]
        return [it for it in items if it.unit_id == uid]
    return list(items)


def _scope_subtopics(scope: str) -> list[str]:
    """The syllabus subtopic tags a scope covers (for the AI pool + generation)."""
    from anki.speedrun import load_topics

    all_tags = [
        f"subtopic::{u['id']}::{s['id']}"
        for u in load_topics()["units"]
        for s in u["subtopics"]
    ]
    if scope.startswith("subtopic:"):
        return [scope[len("subtopic:") :]]
    if scope.startswith("unit:"):
        uid = scope[len("unit:") :]
        return [t for t in all_tags if t.split("::")[1] == uid]
    return all_tags


def _assembled_item(
    item_id: str,
    question: str,
    answer: str,
    subtopic: str,
    unit_id: str,
    difficulty: str,
    source: str,
    generated: bool,
) -> dict[str, Any]:
    """Shape one practice item for the webview as real MULTIPLE CHOICE: the stem
    plus A-E options — genuine embedded ones when present, otherwise plausible
    numeric distractors synthesised around the correct value. The correct letter
    is withheld until submission (graded server-side), so there is no peeking."""
    from anki.speedrun.practice_test import build_mcq

    stem, choices, _correct = build_mcq(question, answer, item_id)
    return {
        "id": item_id,
        "stem": stem,
        "choices": [{"letter": ltr, "text": txt} for ltr, txt in choices],
        "subtopic": subtopic,
        "unitId": unit_id,
        "difficulty": difficulty,
        "source": source,
        "generated": generated,
    }


_BANK_WARM_VERSION = 1


def ensure_practice_bank(col: Any) -> None:
    """Make sure the PRE-BUILT practice bank exists BEFORE any test starts, so a
    question is never generated on the spot (which would add lag and break the
    timed exam). Fills the quarantined pool once per collection with
    deterministic templated (randomized-number) problems — pure math, no AI, no
    model calls — so a full 30-question test is always assemblable offline.
    Verified AI problems, when enabled, are added to the SAME pool separately and
    out of the test flow. Guarded by a config flag (runs a single time) and
    best-effort: a warm-up failure never blocks a test."""
    if col is None:
        return
    try:
        if int(col.get_config("speedrunBankWarmed", 0) or 0) >= _BANK_WARM_VERSION:
            return
        from anki.speedrun.problem_gen import prebuild_templated_bank

        prebuild_templated_bank(col)
        col.set_config("speedrunBankWarmed", _BANK_WARM_VERSION)
    except Exception:  # noqa: BLE001 — bank warm-up must never break a test
        pass


def _bank_sample_items(col: Any, scope: str) -> list:
    """PRE-BUILT bank items for a scope (templated + verified AI, from the
    quarantined pool), as SampleItems so they flow through the same assembly and
    grading path as the held-out corpus. Filtered to items that render as real
    A-E multiple choice. Never the held-out set itself, so there is no leakage."""
    from anki.speedrun.practice_test import is_mcq
    from anki.speedrun.problem_gen import load_pool
    from anki.speedrun.soa_sample import SampleItem

    subs = set(_scope_subtopics(scope))
    out: list[SampleItem] = []
    for p in load_pool(col):
        if p.subtopic_tag not in subs:
            continue
        item = SampleItem(
            id=p.id,
            question=p.question,
            subtopic=p.subtopic_tag,
            difficulty=p.difficulty,
            answer=p.final_answer,
            source=p.source_name,
        )
        if is_mcq(item):
            out.append(item)
    return out


def _assemble_practice_test(
    mw: aqt.main.AnkiQt,
    seed: int,
    size: int,
    scope: str = "all",
) -> dict[str, Any]:
    """Assemble a timed, all-multiple-choice practice test from the PRE-BUILT
    bank — nothing is generated on the spot.

    Every question is drawn first from the OFFICIAL held-out corpus (section-
    weighted across the three units for a whole-exam test), then — only if that
    scoped pool is short — topped up from the pre-built templated / verified-AI
    bank. The pool is filtered to items that can be shown as real A-E multiple
    choice, so a test is 100% MC. Read-only + deterministic given the seed; the
    correct letter is withheld until submit (graded server-side)."""
    import random

    from anki.speedrun.practice_test import assemble_test, is_mcq
    from anki.speedrun.soa_sample import load_corpus

    # One-time, no-lag bank warm-up BEFORE the test (idempotent after the first).
    ensure_practice_bank(mw.col)

    n = max(1, min(size, 60))
    corpus = load_corpus()
    # Official, held-out, MC-capable items for this scope; fall back to the full
    # corpus if a scope matches nothing, so a test is always assembled.
    official = [it for it in _scope_items(corpus.items, scope) if is_mcq(it)]
    if not official and scope != "all":
        official = [it for it in corpus.items if is_mcq(it)]
    chosen = assemble_test(n=n, seed=seed, items=official) if official else []

    # Top up any shortfall (a thin scope) from the pre-built bank, deterministically.
    generated_ids: set[str] = set()
    if len(chosen) < n:
        chosen_ids = {it.id for it in chosen}
        bank = [
            it for it in _bank_sample_items(mw.col, scope) if it.id not in chosen_ids
        ]
        rng = random.Random(seed)
        rng.shuffle(bank)
        topup = bank[: n - len(chosen)]
        generated_ids = {it.id for it in topup}
        chosen = chosen + topup

    return {
        "items": [
            _assembled_item(
                it.id,
                it.question,
                it.answer,
                it.subtopic,
                it.unit_id,
                it.difficulty,
                it.source,
                it.id in generated_ids,
            )
            for it in chosen
        ],
        "corpus": {"source": corpus.source, "isRealSoa": corpus.is_real_soa},
        "seed": seed,
    }


def _set_ai_enabled_cmd(mw: aqt.main.AnkiQt, on: bool) -> None:
    from anki.speedrun.ai import set_ai_enabled

    set_ai_enabled(mw.col, on)


def _speedrun_settings(mw: aqt.main.AnkiQt) -> dict[str, Any]:
    """Current app settings for the home settings strip: the light/dark theme, the
    tiered mastery scheduler (the ablation switch), and whether model-written AI
    practice is on (plus whether a real provider key is present)."""
    from anki.speedrun.ai import ai_enabled, available_provider
    from aqt.theme import theme_manager

    col = mw.col
    return {
        "theme": "dark" if theme_manager.night_mode else "light",
        "masteryScheduler": bool(
            col.get_config("speedrunMasteryScheduler", True) if col else True
        ),
        "guided": bool(col.get_config("speedrunGuidedMode", False)) if col else False,
        "aiEnabled": bool(ai_enabled(col)) if col else False,
        "hasKey": available_provider() == "openai",
    }


def _set_theme_cmd(mw: aqt.main.AnkiQt, dark: bool) -> None:
    """Flip the whole app between light and dark. Uses Anki's own theme so it
    persists and re-styles every window live (the webview updates its night-mode
    class via the theme_did_change hook — no reload needed)."""
    from aqt.theme import Theme

    mw.set_theme(Theme.DARK if dark else Theme.LIGHT)


def _record_practice_test(mw: aqt.main.AnkiQt, payload: str) -> dict[str, Any]:
    from anki.speedrun.practice_test import (
        build_mcq,
        free_response_correct,
        grade,
        record_test,
    )
    from anki.speedrun.problem_gen import load_pool
    from anki.speedrun.soa_sample import SampleItem, load_sample_items

    data = json.loads(payload)
    # Responses carry the student's chosen LETTER (every test is multiple
    # choice), not a self-marked 0/1.
    responses = {str(k): str(v) for k, v in (data.get("responses") or {}).items()}
    ids = [str(i) for i in (data.get("ids") or [])]
    label = str(data.get("label") or "in-app practice test")
    # Test scope ("all" | "unit:<id>" | "subtopic:<tag>") sets the readiness
    # weight together with the source classified below.
    scope_raw = str(data.get("scope") or "all")
    scope_kind = "all" if scope_raw == "all" else scope_raw.split(":", 1)[0]
    # Grade against BOTH the held-out corpus and the verified/templated bank, so
    # bank-topped-up tests also record per-subtopic performance (labelled).
    official = {it.id: it for it in load_sample_items()}
    pool = load_pool(mw.col)
    generated = {
        p.id: SampleItem(
            id=p.id,
            question=p.question,
            subtopic=p.subtopic_tag,
            difficulty=p.difficulty,
            answer=p.final_answer,
            source=p.source_name,
        )
        for p in pool
    }
    solution_by_id = {p.id: p.solution for p in pool}

    items = [official.get(i) or generated.get(i) for i in ids]
    items = [it for it in items if it is not None]

    # Classify the test's SOURCE for its readiness weight: "official" when at
    # least half its graded items came from the held-out corpus, else
    # "generated" (the templated / verified-AI bank). Held-out and generated ids
    # are disjoint, so this is unambiguous.
    official_count = sum(1 for it in items if it.id in official)
    source = "official" if items and official_count * 2 >= len(items) else "generated"

    # Objective grading: a multiple-choice item is right when the chosen letter
    # matches the answer's letter; a free-response item when the typed value
    # matches. No self-marking. The per-item review rows drive the results view.
    graded: dict[str, int] = {}
    review: list[dict[str, Any]] = []
    for it in items:
        given = responses.get(it.id, "")
        # Rebuild the SAME multiple-choice options the UI showed (deterministic per
        # item id), so the correct letter matches exactly. Free-response only when
        # the answer isn't numeric. No self-marking.
        _stem, _choices, letter = build_mcq(it.question, it.answer, it.id)
        if letter is not None:
            ok = given.strip().upper() == letter
        else:
            ok = free_response_correct(given, it.answer) if given.strip() else False
        graded[it.id] = 1 if ok else 0
        review.append(
            {
                "id": it.id,
                "your": given,
                "correct": ok,
                "correctLetter": letter,
                "answer": it.answer,
                "solution": solution_by_id.get(it.id, ""),
            }
        )

    result = grade(items, graded, label=label)
    stats = record_test(mw.col, result, scope=scope_kind, source=source)
    return {
        "questions": result.questions,
        "correct": result.correct,
        "proportion": round(result.proportion, 4),
        "perUnit": {u: list(v) for u, v in result.per_unit.items()},
        "stats": stats,
        "review": review,
    }


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


def set_guided_cmd(mw: aqt.main.AnkiQt, raw: str) -> None:
    """Toggle the guided prerequisite gate (the global free-mode bypass).
    Curriculum ordering only; it never changes any score or the give-up rule."""
    from anki.speedrun import set_guided_mode

    set_guided_mode(mw.col, raw.strip() in ("1", "true", "True", "on"))


def set_scheduler_cmd(mw: aqt.main.AnkiQt, raw: str) -> None:
    """Toggle the three-tier mastery scheduler (Full three-tier order vs plain
    Anki). Read-only reorder in build_queues; never touches FSRS or any score."""
    from anki.speedrun import set_mastery_scheduler

    set_mastery_scheduler(mw.col, raw.strip() in ("1", "true", "True", "on"))


def unlock_subtopic_cmd(mw: aqt.main.AnkiQt, tag: str) -> None:
    """Per-topic gate bypass for an experienced user."""
    from anki.speedrun import unlock_subtopic

    if tag:
        unlock_subtopic(mw.col, tag)


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
    """Open the next thing that's actually due in one click.

    Uses the tier-ordered study plan (blocked → within-unit → cross-unit), which
    the engine already filters to decks with cards due today, so the first item is
    the honest "study next" target — one that always has cards. If nothing is due,
    say so instead of opening an empty deck (which would bounce to the finished
    screen). Never fabricated: it reflects measured due counts + the gate state."""
    from anki import speedrun_pb2
    from anki.speedrun import (
        expected_subtopic_tags,
        subtopic_prereqs,
        subtopic_weights,
        unit_prereqs,
        unit_weights,
    )

    # Pass the DAG so the plan respects the guided gate (an unlocked subtopic),
    # matching what the live queue actually serves. StudyPlan has a single
    # repeated field, so Anki's backend codegen unwraps it: this returns the list
    # of StudyPlanItem directly (not a wrapper with an `.items` attribute).
    items = mw.col._backend.get_study_plan(
        expected_subtopics=expected_subtopic_tags(),
        units=[speedrun_pb2.UnitWeight(unit_id=u, weight=w) for u, w in unit_weights()],
        subtopic_weights=[
            speedrun_pb2.SubtopicWeight(tag=t, weight=w) for t, w in subtopic_weights()
        ],
        subtopic_prereqs=[
            speedrun_pb2.SubtopicPrereqs(tag=t, prereqs=p)
            for t, p in subtopic_prereqs()
        ],
        unit_prereqs=[
            speedrun_pb2.UnitPrereqs(unit_id=u, prereqs=p) for u, p in unit_prereqs()
        ],
    )
    if items and open_deck_by_id(mw, items[0].deck_id):
        return
    tooltip("You're caught up — nothing is due right now.", parent=mw)


# --- Custom home shell (concept map + readiness tabs) ---------------------
# The app's landing screen (the speedrunHome state) renders a full-bleed
# SvelteKit "home" page into mw.web. Its top-bar buttons are routed to the native
# Anki flows here, and the embedded concept-map tab reuses the same study/pace
# bridge commands as the standalone study map.


def _ensure_speedrun_defaults(mw: aqt.main.AnkiQt) -> None:
    """Seed the performance-first DEFAULTS on the open collection so an existing
    (pre-pivot) collection behaves like a freshly built one: the three-tier mastery
    scheduler ON, and the guided gate OFF (the guided sequence stays as advice —
    recommended next topic + arrows — but never withholds cards).

    Only sets a value when it is ABSENT, so a user's later choice in the settings
    strip (e.g. turning the scheduler off for the ablation) persists across reopens."""
    col = mw.col
    if col is None:
        return
    if col.get_config("speedrunMasteryScheduler", None) is None:
        col.set_config("speedrunMasteryScheduler", True)
    if col.get_config("speedrunGuidedMode", None) is None:
        col.set_config("speedrunGuidedMode", False)


def show_home(mw: aqt.main.AnkiQt) -> None:
    """Render the custom home shell into the main webview.

    A caller can request an initial tab (e.g. the daily Plan) by setting
    ``mw._speedrun_home_tab`` before entering the ``speedrunHome`` state; it is
    consumed once and passed to the page as ``?tab=…`` so, say, the end-of-deck
    congrats screen can land the user straight on the Plan."""
    _ensure_speedrun_defaults(mw)
    mw.web.set_bridge_command(lambda cmd: _home_bridge_cmd(mw, cmd), mw)
    tab = getattr(mw, "_speedrun_home_tab", None)
    mw._speedrun_home_tab = None
    page = f"home?tab={tab}" if tab else "home"
    mw.web.load_sveltekit_page(page)


def go_home_tab(mw: aqt.main.AnkiQt, tab: str) -> None:
    """Open the custom home shell on a specific tab (e.g. "plan")."""
    mw._speedrun_home_tab = tab
    mw.moveToState("speedrunHome")


# --- Categorized add-card ---------------------------------------------------
# This is a single-exam app, so a user-added card must be filed under one of the
# 19 syllabus subtopics (never a loose/uncategorized deck). The front is
# classified to suggest a subtopic (real model when AI is on + keyed, else the
# offline keyword baseline, so it works AI-off); the user confirms or overrides,
# then the card is saved into that subtopic's deck. The card text is the user's
# own (not AI-generated), so it counts toward coverage/mastery immediately.


def _classify_card(mw: aqt.main.AnkiQt, front: str) -> dict[str, Any]:
    """Suggest the best-matching subtopics for a typed card front (top 3), each
    with the named source it was matched against. Suggestion only — the user
    picks. Falls back to the keyword baseline when AI is off."""
    from anki.speedrun import subtopic_name
    from anki.speedrun.ai import ai_enabled, available_provider, classify_subtopic_core

    front = front.strip()
    if not front:
        return {"provider": "", "suggestions": []}
    use_ai = ai_enabled(mw.col) and available_provider() == "openai"
    provider = "openai" if use_ai else "stub"
    out: list[dict[str, str]] = []
    for tag, _score, source in classify_subtopic_core(front, provider)[:3]:
        parts = tag.split("::")
        try:
            name = subtopic_name(parts[1], parts[2])
        except (IndexError, KeyError):
            name = tag
        out.append({"tag": tag, "name": name, "source": source})
    return {"provider": provider, "suggestions": out}


def _add_card(mw: aqt.main.AnkiQt, payload: str) -> dict[str, Any]:
    """Save a user-authored flashcard into its subtopic's deck (tagged
    ``subtopic::… + format::flashcard``). Rejects an uncategorized card."""
    from anki.speedrun import deck_name_for_subtopic_tag

    data = json.loads(payload)
    front = str(data.get("front", "")).strip()
    back = str(data.get("back", "")).strip()
    tag = str(data.get("subtopic", "")).strip()
    if not front or not back:
        return {"ok": False, "error": "Enter both a front and a back."}
    deck_name = deck_name_for_subtopic_tag(tag)
    if deck_name is None:
        return {"ok": False, "error": "Pick a subtopic."}
    basic = mw.col.models.by_name("Basic")
    if basic is None:
        return {"ok": False, "error": "Basic note type is missing."}
    parts = tag.split("::")
    did = mw.col.decks.id(deck_name)
    note = mw.col.new_note(basic)
    note["Front"] = front
    note["Back"] = back
    note.add_tag(tag)
    note.add_tag(f"unit::{parts[1]}")
    note.add_tag("format::flashcard")
    mw.col.add_note(note, did)
    return {"ok": True, "deck": deck_name}


# --- Formula sheet (read-only reference) ------------------------------------
# The formula-sheet page shows curated, sourced Exam P formulas plus the user's
# OWN added cards, grouped by subtopic. This bridge returns those user cards. It
# is reference only: it READS notes and never logs a review, schedules a card, or
# changes any score/config (the honesty rule — a reference must not move a
# metric). It sits alongside the unlimited cram deck as a "just let me look /
# practice freely" surface.


def _formula_cards(mw: aqt.main.AnkiQt) -> dict[str, list[dict[str, str]]]:
    """The user's OWN added flashcards, grouped by subtopic tag, for the formula
    sheet's "your added cards" sections. Returns
    ``{subtopic_tag: [{"front", "back"}, ...]}``.

    READ-ONLY: it only searches/reads notes; it never logs a review, schedules,
    or changes any score or config. The pre-seeded curriculum cards are excluded
    (they all carry a ``difficulty::`` tag), so this surfaces just what the user
    added themselves via the categorized Add-card flow (tagged
    ``format::flashcard`` + ``subtopic::…``, with no difficulty tag)."""
    from anki.utils import strip_html

    col = mw.col
    if col is None:
        return {}

    def field(note: Any, name: str) -> str:
        try:
            return strip_html(str(note[name])).strip()
        except KeyError:
            return ""

    try:
        # User-added flashcards only: exclude the seeded cards (difficulty::*).
        note_ids = col.find_notes("tag:format::flashcard -tag:difficulty::*")
    except Exception:  # noqa: BLE001 — a search failure must never break the page
        return {}

    grouped: dict[str, list[dict[str, str]]] = {}
    for nid in note_ids:
        note = col.get_note(nid)
        tag = next((t for t in note.tags if t.startswith("subtopic::")), None)
        if tag is None:
            continue
        front = field(note, "Front")
        back = (
            field(note, "Back") or field(note, "Answer") or field(note, "Explanation")
        )
        if not front and not back:
            continue
        grouped.setdefault(tag, []).append({"front": front, "back": back})
    return grouped


def _home_bridge_cmd(mw: aqt.main.AnkiQt, cmd: str) -> Any:
    # Practice-test data requests need a SYNCHRONOUS return value (the webview
    # bridge JSON-serialises it back to the JS callback). Assembling writes
    # nothing; grading records real evidence. Handle them inline and return.
    if cmd.startswith("speedrun-assemble-test:"):
        seed, size, scope, _source = _test_params(cmd[len("speedrun-assemble-test:") :])
        return _assemble_practice_test(mw, seed, size, scope)
    if cmd == "speedrun-settings":
        return _speedrun_settings(mw)
    if cmd.startswith("speedrun-record-test:"):
        return _record_practice_test(mw, cmd[len("speedrun-record-test:") :])
    if cmd.startswith("speedrun-classify:"):
        return _classify_card(mw, cmd[len("speedrun-classify:") :])
    if cmd.startswith("speedrun-add-card:"):
        return _add_card(mw, cmd[len("speedrun-add-card:") :])
    if cmd == "speedrun-formula-cards":
        # Read-only: the user's own cards for the formula sheet (no writes).
        return _formula_cards(mw)
    # Everything else may move to another state or reload the webview, which must
    # not run from inside the webview's own bridge callback — so defer it.
    QTimer.singleShot(0, lambda: _dispatch_home_cmd(mw, cmd))
    return None


def _home_nav(mw: aqt.main.AnkiQt, where: str) -> None:
    if where == "study":
        study_recommended(mw)
    elif where == "add":
        mw.onAddCard()
    elif where == "browse":
        mw.onBrowse()
    elif where == "stats":
        mw.onStats()
    elif where == "decks":
        mw.moveToState("deckBrowser")
    elif where == "sync":
        mw.on_sync_button_clicked()


def _dispatch_study_cmd(mw: aqt.main.AnkiQt, cmd: str) -> bool:
    """Study / practice / generate commands (open decks, launch practice, kick off
    background problem generation). Returns True if it handled `cmd`."""
    if cmd.startswith("speedrun-study-deck:"):
        try:
            did = int(cmd[len("speedrun-study-deck:") :])
        except ValueError:
            return True
        open_deck_by_id(mw, did)
    elif cmd.startswith("speedrun-study-unit:"):
        open_unit_deck(mw, cmd[len("speedrun-study-unit:") :])
    elif cmd == "speedrun-study-all":
        open_all_deck(mw)
    elif cmd.startswith("speedrun-study:"):
        open_subtopic_deck(mw, cmd[len("speedrun-study:") :])
    elif cmd.startswith("speedrun-practice-unit:"):
        practice_unit(mw, cmd[len("speedrun-practice-unit:") :])
    elif cmd == "speedrun-practice-all":
        practice_all(mw)
    elif cmd.startswith("speedrun-practice:"):
        practice_subtopic(mw, cmd[len("speedrun-practice:") :])
    else:
        return False
    return True


def _dispatch_home_cmd(mw: aqt.main.AnkiQt, cmd: str) -> None:
    def reload() -> None:
        mw.web.load_sveltekit_page("home")

    if cmd.startswith("speedrun-nav:"):
        _home_nav(mw, cmd[len("speedrun-nav:") :])
    elif _dispatch_study_cmd(mw, cmd):
        pass
    elif cmd.startswith("speedrun-set-ai-enabled:"):
        # No reload: the settings strip updates its own state, and the practice
        # screen re-reads AI status when it next opens.
        on = cmd[len("speedrun-set-ai-enabled:") :].strip() in ("1", "true", "on")
        _set_ai_enabled_cmd(mw, on)
    elif cmd.startswith("speedrun-set-theme:"):
        _set_theme_cmd(mw, cmd[len("speedrun-set-theme:") :].strip() == "dark")
    elif cmd.startswith("speedrun-set-exam-date:"):
        set_exam_date_cmd(mw, cmd[len("speedrun-set-exam-date:") :])
        reload()
    elif cmd == "speedrun-clear-exam-date":
        clear_exam_date_cmd(mw)
        reload()
    elif cmd.startswith("speedrun-set-new-per-day:"):
        n = _parse_positive_int(cmd[len("speedrun-set-new-per-day:") :])
        if n is not None:
            set_new_per_day(mw, n)
            reload()
    elif cmd.startswith("speedrun-extend-new:"):
        n = _parse_positive_int(cmd[len("speedrun-extend-new:") :])
        if n is not None:
            extend_new_and_study(mw, n)
    elif cmd.startswith("speedrun-set-guided:"):
        # Write config only; the embedded map re-reads mastery state itself.
        set_guided_cmd(mw, cmd[len("speedrun-set-guided:") :])
    elif cmd.startswith("speedrun-set-scheduler:"):
        set_scheduler_cmd(mw, cmd[len("speedrun-set-scheduler:") :])
    elif cmd.startswith("speedrun-unlock:"):
        unlock_subtopic_cmd(mw, cmd[len("speedrun-unlock:") :])


# --- Reviewer mastery-tier banner ----------------------------------------
# Surfaces which tier the current card's subtopic is in during review
# (Blocked / Within-unit / Cross-unit), so the tier is visible rather than an
# invisible reorder. Registered once from main.py; read-only (no writes).

_TIER_LABELS: dict[int, tuple[str, str]] = {
    0: ("Blocked practice", "#d3a95f"),  # honey — build procedure in isolation
    1: ("Within-unit interleaving", "#8189d6"),  # periwinkle — train recognition
    2: ("Cross-unit review", "#6fa892"),  # sage — spacing
}


def _tier_banner_enabled(col: Collection) -> bool:
    return bool(col.get_config("speedrunTierBanner", True))


def _current_subtopic_tag(card: Card) -> str | None:
    return next((t for t in card.note().tags if t.startswith("subtopic::")), None)


def _tier_for_tag(col: Collection, tag: str) -> tuple[str, str] | None:
    from anki.speedrun import expected_subtopic_tags, subtopic_name

    state = col._backend.get_mastery_state(
        expected_subtopics=expected_subtopic_tags(),
        units=[],
        subtopic_weights=[],
        subtopic_prereqs=[],
        unit_prereqs=[],
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
    # The banner is fixed to the top; we then pad the body by the banner's height
    # plus breathing room so the card is never jammed up under it (the "squished
    # top" fix). Cleared again in _clear_tier_banner.
    js = (
        "(function(){"
        # Sit directly BELOW the custom "← Exam P" bar (measured), never on top of
        # it, and pad the body for both so the card isn't jammed under them.
        "var rb=document.getElementById('speedrun-review-bar');"
        "var rbH=rb?rb.offsetHeight:0;"
        "var b=document.getElementById('speedrun-tier');"
        "if(!b){b=document.createElement('div');b.id='speedrun-tier';"
        "b.style.cssText='position:fixed;left:0;right:0;z-index:2147482000;"
        "text-align:center;font:600 12px/1.4 sans-serif;letter-spacing:0.04em;"
        "padding:7px 14px;pointer-events:none;';document.body.appendChild(b);}"
        "b.style.top=rbH+'px';"
        f"b.textContent={json.dumps(text)};"
        f"b.style.color={json.dumps(color)};"
        f"b.style.background={json.dumps(color + '1f')};"
        f"b.style.borderBottom='1px solid '+{json.dumps(color)};"
        "document.body.style.paddingTop=(rbH+b.offsetHeight+18)+'px';"
        "})();"
    )
    mw.reviewer.web.eval(js)


def _clear_tier_banner(*_args: object) -> None:
    mw = aqt.mw
    if mw is None or mw.reviewer is None or mw.reviewer.web is None:
        return
    mw.reviewer.web.eval(
        "var b=document.getElementById('speedrun-tier'); if(b){b.remove();}"
        "document.body.style.paddingTop='';"
    )


def register_reviewer_banner() -> None:
    """Register the review-time mastery-tier banner hooks. Call once at startup."""
    gui_hooks.reviewer_did_show_question.append(_show_tier_banner)
    gui_hooks.reviewer_did_show_answer.append(_show_tier_banner)
    gui_hooks.reviewer_will_end.append(_clear_tier_banner)


# --- First-run deck seeding (the main deck is not optional) -----------------
# The SOA Exam P deck is built automatically on first open, so the user never
# sees an empty Anki. The logic lives in anki.speedrun.seed (guarded by a
# per-collection flag, so it runs once); here we just wire it to the load hook.


# Anki's v3 scheduler can run a per-collection "Custom scheduling" JS snippet
# (config key ``cardStateCustomizer``), injected into the reviewer on EVERY card
# as ``anki.mutateNextCardStates(...)``. This fork never uses it — the three-tier
# mastery scheduler lives in the Rust engine and is toggled by a config flag — so
# any value there is leftover/experimental. Left in place it breaks review: a JS
# error on every card and, if the snippet touches the ``/_anki/`` backend, Anki's
# "Unexpected API access" guard (card JS is untrusted). Wipe it on load so it can
# never resurface in a demo. One-off equivalent: tools/speedrun/clear_custom_scheduling.py
_CARD_STATE_CUSTOMIZER_KEY = "cardStateCustomizer"


def _clear_stray_custom_scheduling(col: Collection) -> None:
    """Best-effort: clear any stray card-side Custom scheduling JS. Only writes
    when non-empty, so it's a no-op (no sync churn) on every subsequent load."""
    try:
        if col.get_config(_CARD_STATE_CUSTOMIZER_KEY, None):
            col.set_config(_CARD_STATE_CUSTOMIZER_KEY, "")
            print("speedrun: cleared stray card-side Custom scheduling code")
    except Exception:
        import traceback

        traceback.print_exc()


def on_collection_load(col: Collection) -> None:
    """collection_did_load hook: clear stray card JS and ensure the main deck
    exists. Never blocks load (errors are logged, not raised, so the app still
    opens)."""
    # Safety net runs even under the e2e opt-out below: card-side JS scheduling
    # is never part of this fork and would break review regardless of seeding.
    _clear_stray_custom_scheduling(col)
    # Test harnesses (e2e) opt out of seeding so they can exercise the
    # empty-collection honesty/give-up states.
    if os.environ.get("ANKI_SPEEDRUN_NOSEED"):
        return
    try:
        from anki.speedrun.seed import seed_if_missing

        seed_if_missing(col)
    except Exception:
        import traceback

        traceback.print_exc()


def register_collection_hooks() -> None:
    """Register startup hooks that need the collection. Call once at init."""
    gui_hooks.collection_did_load.append(on_collection_load)


# --- App-wide Speedrun theme ----------------------------------------------
# One accent + rounded controls threaded across every Qt screen (browser,
# editor, dialogs) so the app reads as a single custom product, not stock Anki.
# Appended to the app stylesheet via the style_did_init filter hook, so it runs
# on startup and on every theme change, and layers on top of Anki's own styles.

SPEEDRUN_ACCENT = "#8189d6"

_SPEEDRUN_QSS = f"""
/* Speedrun (SOA Exam P) accent + rounded controls */
QPushButton {{
    border-radius: 8px;
    padding: 5px 12px;
}}
QPushButton:default {{
    background-color: {SPEEDRUN_ACCENT};
    color: white;
    border: 1px solid {SPEEDRUN_ACCENT};
}}
QPushButton:default:hover {{
    background-color: #9aa1e0;
}}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    border-radius: 8px;
}}
QTabBar::tab:selected {{
    color: {SPEEDRUN_ACCENT};
}}

/* Thread the accent through item views so the Browse window (sidebar tree +
   card table) and every list/tree dialog read as the custom product, not stock
   Anki. Selection uses the app accent; headers get a little breathing room. */
QTreeView::item:selected,
QTableView::item:selected,
QListView::item:selected,
QTreeWidget::item:selected,
QListWidget::item:selected {{
    background-color: {SPEEDRUN_ACCENT};
    color: white;
}}
QTreeView::item:selected:!active,
QTableView::item:selected:!active,
QListView::item:selected:!active {{
    background-color: rgba(129, 137, 214, 0.45);
    color: white;
}}
QHeaderView::section {{
    padding: 4px 10px;
}}
QTableView, QTreeView, QListView {{
    selection-background-color: {SPEEDRUN_ACCENT};
    selection-color: white;
}}
"""


def _append_theme(buf: str) -> str:
    return buf + _SPEEDRUN_QSS


# --- Font unification --------------------------------------------------------
# Anki's own webviews (reviewer, deck list, overview, answer bar) default to a
# system font, which reads as stock Anki next to the custom app. We reuse the
# woff2 files the SvelteKit build ALREADY ships (served at /_anki/sveltekit/...),
# so every surface renders in the app's Fraunces + DM Sans — no separate font
# pipeline, works offline. Best-effort: if the files aren't found we simply fall
# back to the system stack rather than break a webview.

_APP_BODY_FONT = '"DM Sans Variable", "DM Sans", system-ui, -apple-system, sans-serif'
_APP_HEAD_FONT = '"Fraunces Variable", "Fraunces", Georgia, "Times New Roman", serif'


@cache
def _app_font_face_css() -> str:
    try:
        from aqt.utils import aqt_data_path

        base = aqt_data_path() / "web" / "sveltekit" / "_app" / "immutable" / "assets"

        def first_url(stem: str) -> str | None:
            for p in sorted(base.glob(f"{stem}.*.woff2")):
                return f"/_anki/sveltekit/_app/immutable/assets/{p.name}"
            return None

        out = ""
        if body := first_url("dm-sans-latin-wght-normal"):
            out += (
                '@font-face{font-family:"DM Sans Variable";font-style:normal;'
                "font-weight:100 1000;font-display:swap;"
                f'src:url("{body}") format("woff2");}}'
            )
        if head := first_url("fraunces-latin-wght-normal"):
            out += (
                '@font-face{font-family:"Fraunces Variable";font-style:normal;'
                "font-weight:100 900;font-display:swap;"
                f'src:url("{head}") format("woff2");}}'
            )
        return out
    except Exception:  # noqa: BLE001 — theming is best-effort; never break a webview
        return ""


# Anki's legacy stdHtml surfaces (deck list, overview, the reviewer's answer bar)
# restyled to the app's fonts, accent, and rounded controls so nothing reads as
# stock Anki. No MathJax here, so forcing the body font is safe.
def _chrome_css() -> str:
    return f"""<style>
{_app_font_face_css()}
/* The app doesn't time study — hide Anki's review timer entirely so it's never
   an option, regardless of the deck's "Show timer" setting. */
#time {{ display: none !important; }}
body, button, input, select, textarea, table, td, th, .deck {{
    font-family: {_APP_BODY_FONT} !important;
}}
h1, h2, h3, .title {{ font-family: {_APP_HEAD_FONT} !important; }}
a {{ color: {SPEEDRUN_ACCENT}; }}
a:hover {{ color: #9aa1e0; }}
button {{ border-radius: 8px; padding: 6px 14px; }}
#study {{
    background: {SPEEDRUN_ACCENT}; color: #fff;
    border: 1px solid {SPEEDRUN_ACCENT}; font-weight: 600;
}}
#study:hover {{ background: #9aa1e0; }}
tr.deck td {{ padding-top: 7px; padding-bottom: 7px; }}
tr.deck:hover td {{ background: rgba(129, 137, 214, 0.07); }}
</style>"""


# The reviewer's card area: the app font (kept off MathJax, which sets its own)
# and the styled typed-answer box. The shared "← Exam P" back-bar chrome lives in
# _back_bar_css so the deck list and overview can reuse the exact same bar.
def _reviewer_head_css() -> str:
    return f"""<style>
{_app_font_face_css()}
.card {{ font-family: {_APP_BODY_FONT} !important; }}
#typeans {{
    font-family: {_APP_BODY_FONT};
    border: 2px solid rgba(129, 137, 214, 0.35);
    border-radius: 10px; padding: 8px 12px; outline: none; min-width: 12em;
}}
#typeans:focus {{
    border-color: {SPEEDRUN_ACCENT}; box-shadow: 0 0 0 3px rgba(129, 137, 214, 0.22);
}}
</style>"""


# Styling for the fixed "← Exam P" back bar (see _review_bar_html). It's the single
# one-click way back to the home shell now that Anki's top toolbar is hidden on
# every screen (reviewer, deck list, overview), so the reviewer + deck browser +
# overview all share this exact chrome. Fonts/accent come from _reviewer_head_css /
# _chrome_css injected alongside it; this is just the bar itself.
def _back_bar_css() -> str:
    return f"""<style>
body {{ padding-top: 3.1rem; }}
#speedrun-review-bar {{
    position: fixed; top: 0; left: 0; right: 0; z-index: 2147483000;
    display: flex; align-items: center; gap: 0.75rem;
    height: 3.1rem; box-sizing: border-box; padding: 0 1rem;
    font-family: {_APP_BODY_FONT};
    background: #fdfbf6; border-bottom: 1px solid rgba(129, 137, 214, 0.18);
}}
.night-mode #speedrun-review-bar {{
    background: #221f2b; border-bottom-color: rgba(236, 230, 218, 0.12); color: #ece6da;
}}
#speedrun-review-bar .sr-back {{
    display: inline-flex; align-items: center; gap: 0.35rem;
    border: 1px solid transparent; border-radius: 8px; background: transparent;
    color: {SPEEDRUN_ACCENT}; font-weight: 700; font-size: 0.9rem;
    padding: 0.35rem 0.6rem; cursor: pointer;
}}
#speedrun-review-bar .sr-back:hover {{ background: rgba(129, 137, 214, 0.12); }}
</style>"""


def _review_bar_html() -> str:
    # The shared back-to-home affordance (reviewer, deck list, overview). Just the
    # "← Exam P" button — during review the current subtopic is shown by the
    # mastery-tier banner right below it, so we don't repeat the topic name here.
    return (
        '<div id="speedrun-review-bar">'
        '<button class="sr-back" onclick="pycmd(\'speedrun-home\')" '
        'title="Back to Exam P home">&#8592;&nbsp;Exam&nbsp;P</button>'
        "</div>"
    )


def _on_webview_content(web_content: WebContent, context: object) -> None:
    import aqt.deckbrowser
    import aqt.overview
    import aqt.reviewer

    if isinstance(context, aqt.reviewer.Reviewer):
        web_content.head += _reviewer_head_css() + _back_bar_css()
        web_content.body += _review_bar_html()
    elif isinstance(context, (aqt.deckbrowser.DeckBrowser, aqt.overview.Overview)):
        # Anki's top toolbar is hidden on these screens too (see main.py's
        # _deckBrowserState / _overviewState), so without this they'd have no
        # one-click way back to the home shell. Give them the SAME "← Exam P" bar
        # the reviewer uses — same HTML, same speedrun-home handler (_on_js_message).
        web_content.head += _chrome_css() + _back_bar_css()
        web_content.body += _review_bar_html()
    elif isinstance(context, aqt.reviewer.ReviewerBottomBar):
        web_content.head += _chrome_css()


def _on_js_message(
    handled: tuple[bool, Any], message: str, context: object
) -> tuple[bool, Any]:
    """Route the custom '← Exam P' back button (reviewer, deck list, overview)
    back to the home shell. Deferred so we never tear the webview down from
    inside its own callback."""
    if message == "speedrun-home":
        from aqt import mw

        if mw is not None:
            QTimer.singleShot(0, lambda: mw.moveToState("speedrunHome"))
        return (True, None)
    if message == "speedrun-plan":
        # End-of-deck congrats "Back to plan": open the home shell on the Plan tab.
        from aqt import mw

        if mw is not None:
            QTimer.singleShot(0, lambda: go_home_tab(mw, "plan"))
        return (True, None)
    if message == "speedrun-study-next":
        # End-of-deck congrats "Study next": open the next due deck (tier-ordered),
        # or say we're caught up. Deferred so we don't move states from inside the
        # webview's own callback.
        from aqt import mw

        if mw is not None:
            QTimer.singleShot(0, lambda: study_recommended(mw))
        return (True, None)
    return handled


def load_dotenv_if_present() -> None:
    """Load ``KEY=VALUE`` lines from the repo-root ``.env`` into the process
    environment (without overriding anything already set), so an ``OPENAI_API_KEY``
    placed in ``.env`` is actually picked up — Anki itself never reads ``.env``, it
    only sees ``os.environ``. Best-effort: malformed lines and a missing file are
    ignored, and existing env vars always win. Never logs the value."""
    try:
        env_path = Path(__file__).resolve().parents[2] / ".env"
        if not env_path.exists():
            return
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            if key and key not in os.environ:
                os.environ[key] = val.strip().strip('"').strip("'")
    except Exception:  # noqa: BLE001 — never block startup on .env parsing
        pass


def register_theme() -> None:
    """Make Anki's own screens read as one custom product: thread the accent
    through Qt, unify the fonts (Fraunces + DM Sans) across the reviewer / deck
    list / overview / answer bar, give the reviewer, deck list, and overview a
    custom '← Exam P' back bar in place of Anki's hidden toolbar, and wire that
    bar back to the home shell. Call once at init."""
    gui_hooks.style_did_init.append(_append_theme)
    gui_hooks.webview_will_set_content.append(_on_webview_content)
    gui_hooks.webview_did_receive_js_message.append(_on_js_message)
