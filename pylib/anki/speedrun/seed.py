# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Build a tagged SOA Exam P starter deck for the review loop (7c) and demo.

Cards are static for now; parameterized (regenerating) questions are a later step
for the performance model and the mastery gate. Every card is tagged with its
unit, subtopic, and difficulty so coverage and the scheduler can reason about it.
Subtopics follow the official 2026-05 Exam P learning outcomes; content is
original and uses standard results (no copyrighted exam items).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NamedTuple

from anki.speedrun import (
    apply_prereqs_config,
    apply_subtopic_weights_config,
    difficulty_tag,
    load_topics,
    subtopic_name,
    subtopic_tag,
    unit_name,
    unit_tag,
)

if TYPE_CHECKING:
    from anki.collection import Collection

ROOT_DECK = "SOA Exam P"

# Per-collection flag so the (non-optional) deck is seeded exactly once.
SEEDED_KEY = "speedrunSeeded"

# Notetype for numerical / short-computed questions: the student TYPES the answer
# ({{type:Answer}}) instead of just flipping a flashcard. Memorization cards keep
# the built-in "Basic" front/back reveal. This matches how the exam actually
# tests (compute a value) and the non-flashcard format AI-generated practice uses.
SHORT_ANSWER_NOTETYPE = "SOA Short Answer"

# SeedCard.kind values.
KIND_RECALL = "recall"  # memorization -> flashcard (Basic)
KIND_NUMERIC = "numeric"  # compute / short typed answer -> {{type:Answer}}


class SeedCard(NamedTuple):
    unit_id: str
    subtopic_id: str
    difficulty: str
    front: str
    back: str
    # "recall" (flashcard) by default. "numeric" makes it a typed short-answer
    # card: `answer` is the concise value the student types, and the fuller
    # derivation in `back` becomes the explanation shown after answering.
    kind: str = KIND_RECALL
    answer: str = ""


def format_tag(kind: str) -> str:
    """Tag marking a card's format so the reviewer/analytics can tell typed
    short-answer cards from flashcards."""
    return "format::short_answer" if kind == KIND_NUMERIC else "format::flashcard"


# A starter deck spanning every subtopic in the official outline, with a mix of
# recall ("state the definition") and applied ("solve this") cards at graded
# difficulty. The subtopic ids match exam_p_topics.json.
SEED_CARDS: list[SeedCard] = [
    # --- General Probability ---
    SeedCard(
        "general",
        "sets_axioms",
        "easy",
        "A fair six-sided die is rolled once. Give the sample space and P(even).",
        "S = {1, 2, 3, 4, 5, 6}; even = {2, 4, 6}, so P(even) = 3/6 = 1/2.",
    ),
    SeedCard(
        "general",
        "sets_axioms",
        "easy",
        "State the three axioms of probability.",
        "P(A) >= 0; P(S) = 1; for disjoint events P(union) = sum of the P(A_i).",
    ),
    SeedCard(
        "general",
        "combinatorics",
        "easy",
        "In how many ways can you choose 3 items from 10 when order does not matter?",
        "C(10, 3) = 10! / (3! 7!) = 120.",
        kind=KIND_NUMERIC,
        answer="120",
    ),
    SeedCard(
        "general",
        "combinatorics",
        "medium",
        "From 5 men and 4 women, how many committees of 2 men and 2 women are possible?",
        "C(5, 2) * C(4, 2) = 10 * 6 = 60.",
        kind=KIND_NUMERIC,
        answer="60",
    ),
    SeedCard(
        "general",
        "independence",
        "easy",
        "If events A and B are independent, what is P(A and B)?",
        "P(A and B) = P(A) P(B).",
    ),
    SeedCard(
        "general",
        "independence",
        "medium",
        "A and B are independent with P(A) = 0.3, P(B) = 0.5. Find P(A or B).",
        "P(A or B) = 0.3 + 0.5 - (0.3)(0.5) = 0.65.",
        kind=KIND_NUMERIC,
        answer="0.65",
    ),
    SeedCard(
        "general",
        "add_mult_rules",
        "easy",
        "State the general addition rule for P(A or B).",
        "P(A or B) = P(A) + P(B) - P(A and B).",
    ),
    SeedCard(
        "general",
        "add_mult_rules",
        "easy",
        "State the multiplication rule for P(A and B).",
        "P(A and B) = P(A) P(B | A) = P(B) P(A | B).",
    ),
    SeedCard(
        "general",
        "conditional",
        "easy",
        "State the definition of the conditional probability P(A | B).",
        "P(A | B) = P(A and B) / P(B), for P(B) > 0.",
    ),
    SeedCard(
        "general",
        "conditional",
        "medium",
        "Given P(A and B) = 0.2 and P(B) = 0.4, find P(A | B).",
        "P(A | B) = 0.2 / 0.4 = 0.5.",
        kind=KIND_NUMERIC,
        answer="0.5",
    ),
    SeedCard(
        "general",
        "bayes",
        "medium",
        "State Bayes' theorem for events A and B.",
        "P(A | B) = P(B | A) P(A) / P(B).",
    ),
    SeedCard(
        "general",
        "bayes",
        "hard",
        "A disease affects 1% of people. A test is 99% sensitive and 95% specific. "
        "Given a positive test, find P(disease).",
        "P = (0.99)(0.01) / [(0.99)(0.01) + (0.05)(0.99)] = 0.0099 / 0.0594 ~= 0.167.",
        kind=KIND_NUMERIC,
        answer="0.167",
    ),
    # --- Univariate Random Variables ---
    SeedCard(
        "univariate",
        "rv_basics",
        "easy",
        "How is the CDF F(x) of a random variable X defined?",
        "F(x) = P(X <= x).",
    ),
    SeedCard(
        "univariate",
        "rv_basics",
        "medium",
        "For a continuous X, relate the pdf f and the cdf F.",
        "f(x) = F'(x); F(x) = integral of f(t) dt from -infinity to x.",
    ),
    SeedCard(
        "univariate",
        "expectation",
        "easy",
        "Define E[X] for a continuous X with density f.",
        "E[X] = integral of x f(x) dx over the support.",
    ),
    SeedCard(
        "univariate",
        "expectation",
        "medium",
        "Give the k-th raw moment of a continuous X.",
        "E[X^k] = integral of x^k f(x) dx.",
    ),
    SeedCard(
        "univariate",
        "expectation",
        "medium",
        "How do you find the median m of a continuous X?",
        "Solve F(m) = 0.5.",
    ),
    SeedCard(
        "univariate",
        "variance",
        "easy",
        "Write Var(X) in terms of moments.",
        "Var(X) = E[X^2] - (E[X])^2.",
    ),
    SeedCard(
        "univariate",
        "variance",
        "medium",
        "Define the coefficient of variation of X.",
        "CV = sd(X) / E[X].",
    ),
    SeedCard(
        "univariate",
        "discrete_dists",
        "easy",
        "For X ~ Binomial(n, p), give E[X] and Var(X).",
        "E[X] = n p, Var(X) = n p (1 - p).",
    ),
    SeedCard(
        "univariate",
        "discrete_dists",
        "medium",
        "For X ~ Poisson(lambda), give E[X] and Var(X).",
        "E[X] = Var(X) = lambda.",
    ),
    SeedCard(
        "univariate",
        "discrete_dists",
        "medium",
        "For X ~ Poisson(3), find P(X = 0).",
        "P(X = 0) = e^(-3) ~= 0.0498.",
        kind=KIND_NUMERIC,
        answer="0.0498",
    ),
    SeedCard(
        "univariate",
        "continuous_dists",
        "easy",
        "For X ~ Exponential with rate lambda, give E[X] and Var(X).",
        "E[X] = 1 / lambda, Var(X) = 1 / lambda^2.",
    ),
    SeedCard(
        "univariate",
        "continuous_dists",
        "medium",
        "For X ~ Uniform(a, b), give E[X] and Var(X).",
        "E[X] = (a + b) / 2, Var(X) = (b - a)^2 / 12.",
    ),
    SeedCard(
        "univariate",
        "continuous_dists",
        "medium",
        "X ~ Uniform(0, 1) and Y = -ln(X). Identify the distribution of Y.",
        "Y ~ Exponential(1): F_Y(y) = 1 - e^(-y) for y > 0.",
        kind=KIND_NUMERIC,
        answer="Exponential(1)",
    ),
    SeedCard(
        "univariate",
        "insurance_apps",
        "easy",
        "Loss X with an ordinary deductible d: write the payment per loss.",
        "Payment = (X - d)_+ = max(X - d, 0).",
    ),
    SeedCard(
        "univariate",
        "insurance_apps",
        "medium",
        "Loss X with deductible d and maximum covered loss u: payment per loss?",
        "Payment = min(X, u) - min(X, d).",
    ),
    # --- Multivariate Random Variables ---
    SeedCard(
        "multivariate",
        "joint_distributions",
        "easy",
        "For a joint density f(x, y), how do you get P((X, Y) in region A)?",
        "Integrate f(x, y) over A (a double integral).",
    ),
    SeedCard(
        "multivariate",
        "joint_distributions",
        "medium",
        "State the condition for X and Y to be independent via the joint density.",
        "f(x, y) = f_X(x) f_Y(y) for all x, y.",
    ),
    SeedCard(
        "multivariate",
        "marginal_conditional",
        "easy",
        "Given joint density f(x, y), give the marginal density f_X(x).",
        "f_X(x) = integral of f(x, y) dy over all y.",
    ),
    SeedCard(
        "multivariate",
        "marginal_conditional",
        "medium",
        "Give the conditional density f_(Y|X)(y | x).",
        "f_(Y|X)(y | x) = f(x, y) / f_X(x), for f_X(x) > 0.",
    ),
    SeedCard(
        "multivariate",
        "joint_moments",
        "medium",
        "For a joint density f(x, y), give E[g(X, Y)].",
        "E[g(X, Y)] = double integral of g(x, y) f(x, y) dx dy.",
    ),
    SeedCard(
        "multivariate",
        "joint_moments",
        "medium",
        "State the double-expectation (tower) rule for E[X].",
        "E[X] = E[ E[X | Y] ].",
    ),
    SeedCard(
        "multivariate",
        "covariance_correlation",
        "easy",
        "Define Cov(X, Y) in terms of expectations.",
        "Cov(X, Y) = E[XY] - E[X] E[Y].",
    ),
    SeedCard(
        "multivariate",
        "covariance_correlation",
        "medium",
        "Define the correlation coefficient rho(X, Y).",
        "rho = Cov(X, Y) / (sd(X) sd(Y)).",
    ),
    SeedCard(
        "multivariate",
        "covariance_correlation",
        "easy",
        "If X and Y are independent, what is Cov(X, Y)?",
        "Cov(X, Y) = 0 (the converse need not hold).",
    ),
    SeedCard(
        "multivariate",
        "order_statistics",
        "medium",
        "For iid X_1..X_n with cdf F, give the cdf of the maximum X_(n).",
        "P(X_(n) <= x) = [F(x)]^n.",
    ),
    SeedCard(
        "multivariate",
        "order_statistics",
        "medium",
        "For iid X_1..X_n with cdf F, give the cdf of the minimum X_(1).",
        "P(X_(1) <= x) = 1 - [1 - F(x)]^n.",
    ),
    SeedCard(
        "multivariate",
        "linear_combinations",
        "medium",
        "Give Var(aX + bY) in general (including covariance).",
        "a^2 Var(X) + b^2 Var(Y) + 2 a b Cov(X, Y).",
    ),
    SeedCard(
        "multivariate",
        "linear_combinations",
        "hard",
        "For independent X and Y, give Var(aX + bY).",
        "a^2 Var(X) + b^2 Var(Y).",
    ),
    SeedCard(
        "multivariate",
        "clt",
        "medium",
        "State the Central Limit Theorem for the sample mean Xbar of n iid variables.",
        "For large n, Xbar is approximately Normal(mu, sigma^2 / n).",
    ),
    SeedCard(
        "multivariate",
        "clt",
        "hard",
        "n = 100 iid values with mu = 50, sigma = 10. Approximate P(Xbar > 52).",
        "SE = 10 / sqrt(100) = 1; Z = (52 - 50) / 1 = 2; P(Z > 2) ~= 0.0228.",
        kind=KIND_NUMERIC,
        answer="0.0228",
    ),
]


def ensure_short_answer_notetype(col: Collection) -> Any:
    """Get (or create) the "SOA Short Answer" notetype: Front / Answer /
    Explanation, with a ``{{type:Answer}}`` typed-input template so numerical
    questions are answered by typing, not flipping. Idempotent."""
    existing = col.models.by_name(SHORT_ANSWER_NOTETYPE)
    if existing is not None:
        return existing
    mm = col.models
    notetype = mm.new(SHORT_ANSWER_NOTETYPE)
    for field_name in ("Front", "Answer", "Explanation"):
        mm.add_field(notetype, mm.new_field(field_name))
    template = mm.new_template("Card 1")
    template["qfmt"] = '{{Front}}\n\n<hr class="sa-rule">\n\n{{type:Answer}}'
    template["afmt"] = (
        '{{Front}}\n\n<hr id="answer">\n\n{{type:Answer}}\n\n'
        '{{#Explanation}}<div class="sa-expl">{{Explanation}}</div>{{/Explanation}}'
    )
    mm.add_template(notetype, template)
    mm.add(notetype)  # mutates `notetype` with its new id + ordinals
    return notetype


def build_deck(col: Collection, root: str = ROOT_DECK) -> int:
    """Create the tagged Exam P deck in ``col``. Returns the number of cards added.

    Numerical questions become typed short-answer cards (SOA Short Answer,
    ``{{type:Answer}}``); memorization stays flashcard (Basic front/back).
    """
    topics = load_topics()
    basic = col.models.by_name("Basic")
    if basic is None:
        raise RuntimeError("Basic notetype not found in collection")
    short_answer = ensure_short_answer_notetype(col)

    added = 0
    for card in SEED_CARDS:
        deck_name = "::".join(
            [
                root,
                unit_name(card.unit_id, topics),
                subtopic_name(card.unit_id, card.subtopic_id, topics),
            ]
        )
        deck_id = col.decks.id(deck_name)
        assert deck_id is not None
        if card.kind == KIND_NUMERIC:
            note = col.new_note(short_answer)
            note["Front"] = card.front
            note["Answer"] = card.answer
            note["Explanation"] = card.back
        else:
            note = col.new_note(basic)
            note["Front"] = card.front
            note["Back"] = card.back
        note.add_tag(unit_tag(card.unit_id))
        note.add_tag(subtopic_tag(card.unit_id, card.subtopic_id))
        note.add_tag(difficulty_tag(card.difficulty))
        note.add_tag(format_tag(card.kind))
        col.add_note(note, deck_id)
        added += 1
    # Make the per-subtopic weights available to the engine's points-at-stake
    # live review order (ordering only; never affects any score).
    apply_subtopic_weights_config(col, topics)
    # Write the guided-learning DAG (subtopic/unit prerequisites) so the live
    # new-card gate can lock topics until their prerequisites are satisfied.
    apply_prereqs_config(col, topics)
    return added


def seed_if_missing(col: Collection) -> bool:
    """Ensure the (non-optional) SOA Exam P deck exists: the app auto-builds it on
    first open so the user never sees an empty collection. Runs once per
    collection, guarded by ``SEEDED_KEY``; safe to call on every collection load
    (including profile switches). Returns True only if it built the deck now.
    """
    if col.get_config(SEEDED_KEY, False):
        return False
    if col.decks.id_for_name(ROOT_DECK) is not None:
        # Already present (e.g. imported) — just record it so we don't rebuild.
        col.set_config(SEEDED_KEY, True)
        return False
    build_deck(col)
    col.set_config(SEEDED_KEY, True)
    return True
