# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""AI gateway for the SOA Exam P Speedrun fork (Friday AI layer).

Every model-backed feature goes through this module so they share ONE hard
off-switch. AI is OFF by default: with it off, readiness, the study map, and the
deck all work unchanged, and the Rust engine never depends on AI.

Design (see ``docs/ai-features-prd.md``):

- **Provider-agnostic.** A small ``LlmClient`` interface with two providers: an
  ``OpenAiClient`` (real model, key from ``OPENAI_API_KEY``) and a deterministic
  ``StubClient`` (no network, no key) so evals, tests, and CI are re-runnable and
  the app works with AI off. The stub's card generator is also the extraction
  BASELINE the real model must beat.
- **Source-traced.** Every generated card is stamped with the named source it was
  grounded in (``src::<source>``) and lands tagged ``ai::unreviewed`` with a
  ``subtopic_candidate::`` tag (NOT the real ``subtopic::`` tag), so AI output
  never counts toward coverage/mastery until a human approves it. No AI output is
  ever shown without a source.
- **Audited.** Every model call appends ``{feature, model, prompt_hash, source,
  output}`` to a local JSONL, so results are reproducible and auditable.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from anki.speedrun import load_topics, subtopic_name

if TYPE_CHECKING:
    from anki.collection import Collection

# --- config keys + off-switch --------------------------------------------

# Collection-config key. Absent/false => AI disabled (the default).
AI_ENABLED_KEY = "speedrunAiEnabled"
# Which provider to use when AI is on ("openai" or "stub"). Absent => auto: the
# real provider if a key is available, else the offline stub.
AI_PROVIDER_KEY = "speedrunAiProvider"
# OpenAI model to use (overridable so we are not pinned to one).
AI_MODEL_KEY = "speedrunAiModel"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"

# Tags that keep AI output quarantined until a human approves it.
AI_UNREVIEWED_TAG = "ai::unreviewed"
SUBTOPIC_CANDIDATE_PREFIX = "subtopic_candidate"

AI_DECK = "SOA Exam P::AI (unreviewed)"


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

    Every AI function (classify_subtopic, generate_cards, ...) calls this first,
    so there is a single, testable enforcement point for "AI off".
    """
    if not ai_enabled(col):
        raise AiDisabledError(
            "AI is disabled. Enable it in settings to use this feature; "
            "the app still produces all scores with AI off."
        )


# --- provider clients ----------------------------------------------------


@dataclass(frozen=True)
class GeneratedCard:
    """One generated Q/A card, always carrying the named source it came from."""

    front: str
    back: str
    source_name: str
    subtopic_tag: str
    model: str


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "source"


def _sentences(passage: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", passage.strip())
    return [p.strip() for p in parts if len(p.strip()) > 8]


class LlmClient:
    """Minimal provider interface. ``name`` identifies the model in the audit log."""

    name: str = "base"

    def classify(
        self, question: str, labels: list[tuple[str, str]]
    ) -> list[tuple[str, float]]:
        raise NotImplementedError

    def generate(
        self, subtopic_name_: str, source_name: str, source_passage: str, n: int
    ) -> list[tuple[str, str]]:
        raise NotImplementedError


class StubClient(LlmClient):
    """Deterministic, offline provider. No network, no key.

    - ``classify``: keyword overlap between the question and each subtopic name.
    - ``generate``: template/extraction cards from the source passage. This IS
      the extraction baseline the real model must beat (rubric: beat a simpler
      method), so it is deliberately simple but grounded and source-stamped.
    """

    name = "stub-extraction"

    def classify(
        self, question: str, labels: list[tuple[str, str]]
    ) -> list[tuple[str, float]]:
        q = set(re.findall(r"[a-z]+", question.lower()))
        scored: list[tuple[str, float]] = []
        for tag, label in labels:
            terms = set(re.findall(r"[a-z]+", label.lower()))
            overlap = len(q & terms) / (len(terms) or 1)
            scored.append((tag, overlap))
        scored.sort(key=lambda t: (-t[1], t[0]))
        return scored

    def generate(
        self, subtopic_name_: str, source_name: str, source_passage: str, n: int
    ) -> list[tuple[str, str]]:
        sents = _sentences(source_passage) or [source_passage.strip()]
        out: list[tuple[str, str]] = []
        for i in range(n):
            sent = sents[i % len(sents)]
            # Cloze-style extraction: blank the last content word.
            words = sent.split()
            key = words[-1].rstrip(".") if words else sent
            front = f"[{subtopic_name_}] Fill in the blank: " + " ".join(
                words[:-1] + ["_____."]
            )
            back = f"{key}. (source: {source_name})"
            out.append((front, back))
        return out


class OpenAiClient(LlmClient):
    """OpenAI-backed provider. Reads the key from ``OPENAI_API_KEY``; the model is
    configurable. Imports ``openai`` lazily so this module loads without it."""

    def __init__(self, model: str = DEFAULT_OPENAI_MODEL) -> None:
        self.model = model
        self.name = f"openai:{model}"

    def _client(self) -> Any:
        # lazy: only needed when actually calling out; optional dependency.
        from openai import OpenAI  # type: ignore[import-not-found]

        return OpenAI()

    def _chat_json(self, system: str, user: str) -> Any:
        resp = self._client().chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content or "{}")

    def classify(
        self, question: str, labels: list[tuple[str, str]]
    ) -> list[tuple[str, float]]:
        catalog = "\n".join(f"- {tag}: {label}" for tag, label in labels)
        system = (
            "You classify a probability exam question into the single best SOA "
            'Exam P subtopic from a fixed list. Return JSON {"ranked": [tags]} '
            "with up to 3 subtopic tags, best first. Use ONLY tags from the list."
        )
        user = f"Subtopics:\n{catalog}\n\nQuestion: {question}"
        data = self._chat_json(system, user)
        valid = {tag for tag, _ in labels}
        ranked = [t for t in data.get("ranked", []) if t in valid]
        # Descending pseudo-scores so downstream can treat it like the baseline.
        return [(t, float(len(ranked) - i)) for i, t in enumerate(ranked)]

    def generate(
        self, subtopic_name_: str, source_name: str, source_passage: str, n: int
    ) -> list[tuple[str, str]]:
        system = (
            "You write exam-style flashcards for SOA Exam P. Ground every card "
            "ONLY in the provided source; do not add facts not supported by it. "
            'Return JSON {"cards": [{"front": ..., "back": ...}]}.'
        )
        user = (
            f"Subtopic: {subtopic_name_}\nSource ({source_name}):\n{source_passage}\n\n"
            f"Write {n} cards grounded only in this source."
        )
        data = self._chat_json(system, user)
        out: list[tuple[str, str]] = []
        for card in data.get("cards", [])[:n]:
            front = str(card.get("front", "")).strip()
            back = str(card.get("back", "")).strip()
            if front and back:
                out.append((front, back))
        return out


def available_provider() -> str | None:
    """The real provider available in this environment, or None.

    Returns ``"openai"`` when a key is present and the ``openai`` package can be
    imported; otherwise None (so eval harnesses skip the AI side honestly and the
    app falls back to the deterministic stub / baseline)."""
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    try:
        import openai  # type: ignore[import-not-found] # noqa: F401
    except Exception:  # noqa: BLE001
        return None
    return "openai"


def make_client(provider: str, model: str = DEFAULT_OPENAI_MODEL) -> LlmClient:
    if provider == "openai":
        return OpenAiClient(model)
    return StubClient()


def get_client(col: Collection) -> LlmClient:
    """The client for this collection: explicit config provider, else the real
    provider if available, else the offline stub."""
    provider = col.get_config(AI_PROVIDER_KEY, None) or available_provider() or "stub"
    model = col.get_config(AI_MODEL_KEY, None) or DEFAULT_OPENAI_MODEL
    return make_client(provider, model)


# --- feature 1: subtopic classifier --------------------------------------


def subtopic_labels(topics: dict[str, Any] | None = None) -> list[tuple[str, str]]:
    """(tag, human name) for every syllabus subtopic — the classifier's allowed
    labels and its only "index" (the syllabus outcome text). Gold items never
    appear here, so there is no leakage."""
    topics = topics or load_topics()
    out: list[tuple[str, str]] = []
    for unit in topics["units"]:
        for sub in unit["subtopics"]:
            tag = f"subtopic::{unit['id']}::{sub['id']}"
            out.append((tag, f"{unit['name']} / {sub['name']}"))
    return out


def classify_subtopic_core(
    question: str, provider: str, model: str = DEFAULT_OPENAI_MODEL
) -> list[tuple[str, str, str]]:
    """Rank subtopics for a question with the given provider (no collection, so
    the dev eval can measure the model directly). Returns ``(tag, score, source)``
    where ``source`` is the syllabus outcome text the match is grounded in —
    every AI output traces to a named source."""
    labels = subtopic_labels()
    label_by_tag = dict(labels)
    ranked = make_client(provider, model).classify(question, labels)
    return [(tag, str(score), label_by_tag.get(tag, "")) for tag, score in ranked]


def classify_subtopic(col: Collection, question: str) -> list[dict[str, str]]:
    """Collection-gated classifier (respects the off-switch). Suggestions stay in
    a separate area until the user accepts one; each carries its source."""
    require_ai(col)
    provider = col.get_config(AI_PROVIDER_KEY, None) or available_provider() or "stub"
    model = col.get_config(AI_MODEL_KEY, None) or DEFAULT_OPENAI_MODEL
    ranked = classify_subtopic_core(question, provider, model)
    _audit(
        col,
        feature="classify",
        model=make_client(provider, model).name,
        source="syllabus-outcomes",
        prompt=question,
        output=[t for t, _s, _src in ranked[:3]],
    )
    return [{"subtopic": t, "score": s, "source": src} for t, s, src in ranked[:3]]


# --- feature 2: card generation from a named source ----------------------


def generate_cards(
    col: Collection,
    subtopic_tag: str,
    source_name: str,
    source_passage: str,
    n: int = 5,
) -> list[GeneratedCard]:
    """Generate ``n`` source-grounded cards for a subtopic (off-switch enforced).
    Each card carries the named source; nothing is added to the collection here.
    """
    require_ai(col)
    parts = subtopic_tag.split("::")
    name = subtopic_name(parts[1], parts[2]) if len(parts) == 3 else subtopic_tag
    client = get_client(col)
    pairs = client.generate(name, source_name, source_passage, n)
    cards = [
        GeneratedCard(
            front=f,
            back=b,
            source_name=source_name,
            subtopic_tag=subtopic_tag,
            model=client.name,
        )
        for f, b in pairs
    ]
    _audit(
        col,
        feature="generate",
        model=client.name,
        source=source_name,
        prompt=f"{subtopic_tag}: {source_passage}",
        output=[{"front": c.front, "back": c.back} for c in cards],
    )
    return cards


def candidate_tag(subtopic_tag: str) -> str:
    """Turn ``subtopic::u::s`` into ``subtopic_candidate::u::s`` so generated
    cards are NOT counted as real syllabus coverage/mastery until approved."""
    return subtopic_tag.replace("subtopic::", f"{SUBTOPIC_CANDIDATE_PREFIX}::", 1)


def add_generated_cards(
    col: Collection, cards: list[GeneratedCard], deck_name: str = AI_DECK
) -> list[int]:
    """Add generated cards to a quarantine deck, tagged ``ai::unreviewed`` +
    ``src::<source>`` + ``subtopic_candidate::``. They never carry the real
    ``subtopic::`` tag, so coverage/mastery are unaffected until a human
    approves. Returns the new note ids."""
    notetype = col.models.by_name("Basic")
    if notetype is None:
        raise RuntimeError("Basic notetype not found")
    deck_id = col.decks.id(deck_name)
    assert deck_id is not None
    note_ids: list[int] = []
    for c in cards:
        note = col.new_note(notetype)
        note["Front"] = c.front
        note["Back"] = c.back
        note.add_tag(AI_UNREVIEWED_TAG)
        note.add_tag(f"src::{_slug(c.source_name)}")
        note.add_tag(candidate_tag(c.subtopic_tag))
        col.add_note(note, deck_id)
        note_ids.append(note.id)
    return note_ids


def approve_generated_note(col: Collection, note_id: int) -> None:
    """Promote a human-approved AI card: swap its ``subtopic_candidate::`` tag for
    the real ``subtopic::`` tag and drop ``ai::unreviewed`` so it now counts."""
    note = col.get_note(note_id)  # type: ignore[arg-type]
    new_tags: list[str] = []
    for t in note.tags:
        if t == AI_UNREVIEWED_TAG:
            continue
        if t.startswith(f"{SUBTOPIC_CANDIDATE_PREFIX}::"):
            t = t.replace(f"{SUBTOPIC_CANDIDATE_PREFIX}::", "subtopic::", 1)
        new_tags.append(t)
    note.tags = new_tags
    col.update_note(note)


# --- audit log -----------------------------------------------------------


def _audit_path(col: Collection) -> Path:
    return Path(col.path).with_name("speedrun_ai_audit.jsonl")


def _audit(
    col: Collection,
    *,
    feature: str,
    model: str,
    source: str,
    prompt: str,
    output: Any,
) -> None:
    """Append one auditable record per model call so results are reproducible and
    every output traces to a named source. Never raises into the caller."""
    entry = {
        "at": int(time.time()),
        "feature": feature,
        "model": model,
        "source": source,
        "prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16],
        "output": output,
    }
    try:
        with open(_audit_path(col), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass
