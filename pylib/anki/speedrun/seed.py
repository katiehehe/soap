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

# Every seeded study-deck card is a stock **Basic** front/back flashcard that the
# student self-grades (Again/Hard/Good/Easy) — we trust the learner to be honest.
# Computational cards simply show the concise answer plus the worked solution on
# the Back (see ``basic_back``); we no longer force a typed ``{{type:Answer}}``
# numeric entry, which didn't do the worked answers justice. The "SOA Short
# Answer" typed notetype defined below is retained ONLY for the AI-generated
# *quarantine* deck (see ``anki.speedrun.ai``); ``build_deck`` never creates it.
SHORT_ANSWER_NOTETYPE = "SOA Short Answer"

# SeedCard.kind values. Both render as Basic flip cards; "numeric" just gets a
# richer Back (the answer + worked solution), built by ``basic_back``.
KIND_RECALL = "recall"  # memorization / definition -> plain Front/Back
KIND_NUMERIC = "numeric"  # compute -> Back shows the answer + worked solution


class SeedCard(NamedTuple):
    unit_id: str
    subtopic_id: str
    difficulty: str
    front: str
    back: str
    # "recall" (a definition/fact flashcard) by default. "numeric" marks a
    # computational card: `answer` is the concise final value and `back` is the
    # worked solution; on the Basic card the two are combined onto the Back.
    kind: str = KIND_RECALL
    answer: str = ""


# A starter deck spanning every subtopic in the official outline, with a mix of
# recall ("state the definition") and applied ("solve this") cards at graded
# difficulty. The subtopic ids match exam_p_topics.json.
SEED_CARDS: list[SeedCard] = [
    # --- General Probability ---
    SeedCard(
        "general",
        "sets_axioms",
        "easy",
        r"A fair six-sided die is rolled once. Give the sample space and \(P(\text{even})\).",
        r"\(S = \{1,2,3,4,5,6\}\); the even outcomes are \(\{2,4,6\}\), so "
        r"\(P(\text{even}) = \tfrac{3}{6} = \tfrac{1}{2}\).",
    ),
    SeedCard(
        "general",
        "sets_axioms",
        "easy",
        "State the three axioms of probability.",
        r"\(P(A) \ge 0\) for every event; \(P(S) = 1\); and for mutually exclusive "
        r"events, \(P\!\left(\bigcup_i A_i\right) = \sum_i P(A_i)\).",
    ),
    SeedCard(
        "general",
        "combinatorics",
        "easy",
        "In how many ways can you choose 3 items from 10 when order does not matter?",
        "Order doesn't matter, so this is a combination: "
        r"\[ \binom{10}{3} = \frac{10!}{3!\,7!} "
        r"= \frac{10 \cdot 9 \cdot 8}{3 \cdot 2 \cdot 1} = 120. \]",
        kind=KIND_NUMERIC,
        answer="120",
    ),
    SeedCard(
        "general",
        "combinatorics",
        "medium",
        "From 5 men and 4 women, how many committees of 2 men and 2 women are possible?",
        r"\[ \binom{5}{2}\binom{4}{2} = 10 \cdot 6 = 60. \]",
        kind=KIND_NUMERIC,
        answer="60",
    ),
    SeedCard(
        "general",
        "independence",
        "easy",
        r"If events \(A\) and \(B\) are independent, what is \(P(A \cap B)\)?",
        r"\(P(A \cap B) = P(A)\,P(B)\).",
    ),
    SeedCard(
        "general",
        "independence",
        "medium",
        r"\(A\) and \(B\) are independent with \(P(A) = 0.3\), \(P(B) = 0.5\). Find \(P(A \cup B)\).",
        r"\[ P(A \cup B) = 0.3 + 0.5 - (0.3)(0.5) = 0.65. \]",
        kind=KIND_NUMERIC,
        answer="0.65",
    ),
    SeedCard(
        "general",
        "add_mult_rules",
        "easy",
        r"State the general addition rule for \(P(A \cup B)\).",
        r"\(P(A \cup B) = P(A) + P(B) - P(A \cap B)\).",
    ),
    SeedCard(
        "general",
        "add_mult_rules",
        "easy",
        r"State the multiplication rule for \(P(A \cap B)\).",
        r"\(P(A \cap B) = P(A)\,P(B \mid A) = P(B)\,P(A \mid B)\).",
    ),
    SeedCard(
        "general",
        "conditional",
        "easy",
        r"State the definition of the conditional probability \(P(A \mid B)\).",
        r"\(P(A \mid B) = \dfrac{P(A \cap B)}{P(B)}\), for \(P(B) > 0\).",
    ),
    SeedCard(
        "general",
        "conditional",
        "medium",
        r"Given \(P(A \cap B) = 0.2\) and \(P(B) = 0.4\), find \(P(A \mid B)\).",
        r"\[ P(A \mid B) = \frac{0.2}{0.4} = 0.5. \]",
        kind=KIND_NUMERIC,
        answer="0.5",
    ),
    SeedCard(
        "general",
        "bayes",
        "medium",
        r"State Bayes' theorem for events \(A\) and \(B\).",
        r"\(P(A \mid B) = \dfrac{P(B \mid A)\,P(A)}{P(B)}\).",
    ),
    SeedCard(
        "general",
        "bayes",
        "hard",
        "A disease affects 1% of people. A test is 99% sensitive and 95% specific. "
        "Given a positive test, find \\(P(\\text{disease} \\mid +)\\).",
        "With \\(P(D)=0.01\\), \\(P(+\\mid D)=0.99\\), and "
        "\\(P(+\\mid D^{c})=1-0.95=0.05\\), Bayes' theorem gives "
        "\\[ P(D \\mid +) = \\frac{P(+\\mid D)\\,P(D)}"
        "{P(+\\mid D)\\,P(D) + P(+\\mid D^{c})\\,P(D^{c})} "
        "= \\frac{(0.99)(0.01)}{(0.99)(0.01) + (0.05)(0.99)} "
        "= \\frac{0.0099}{0.0594} \\approx 0.167. \\] "
        "Even after a positive test the probability stays low, because the "
        "disease is rare (the base-rate effect).",
        kind=KIND_NUMERIC,
        answer="0.167",
    ),
    # --- Univariate Random Variables ---
    SeedCard(
        "univariate",
        "rv_basics",
        "easy",
        r"How is the CDF \(F(x)\) of a random variable \(X\) defined?",
        r"\(F(x) = P(X \le x)\).",
    ),
    SeedCard(
        "univariate",
        "rv_basics",
        "medium",
        r"For a continuous \(X\), relate the pdf \(f\) and the cdf \(F\).",
        r"\(f(x) = F'(x)\); \(F(x) = \displaystyle\int_{-\infty}^{x} f(t)\,dt\).",
    ),
    SeedCard(
        "univariate",
        "expectation",
        "easy",
        r"Define \(E[X]\) for a continuous \(X\) with density \(f\).",
        r"\(E[X] = \displaystyle\int x\,f(x)\,dx\) over the support.",
    ),
    SeedCard(
        "univariate",
        "expectation",
        "medium",
        r"Give the \(k\)-th raw moment of a continuous \(X\).",
        r"\(E[X^k] = \displaystyle\int x^k f(x)\,dx\).",
    ),
    SeedCard(
        "univariate",
        "expectation",
        "medium",
        r"How do you find the median \(m\) of a continuous \(X\)?",
        r"Solve \(F(m) = 0.5\).",
    ),
    SeedCard(
        "univariate",
        "variance",
        "easy",
        r"Write \(\mathrm{Var}(X)\) in terms of moments.",
        r"\(\mathrm{Var}(X) = E[X^2] - (E[X])^2\).",
    ),
    SeedCard(
        "univariate",
        "variance",
        "medium",
        r"Define the coefficient of variation of \(X\).",
        r"\(\mathrm{CV} = \dfrac{\mathrm{SD}(X)}{E[X]}\).",
    ),
    SeedCard(
        "univariate",
        "discrete_dists",
        "easy",
        r"For \(X \sim \text{Binomial}(n, p)\), give \(E[X]\).",
        r"\(E[X] = np\).",
    ),
    SeedCard(
        "univariate",
        "discrete_dists",
        "easy",
        r"For \(X \sim \text{Binomial}(n, p)\), give \(\mathrm{Var}(X)\).",
        r"\(\mathrm{Var}(X) = np(1 - p)\).",
    ),
    SeedCard(
        "univariate",
        "discrete_dists",
        "medium",
        r"For \(X \sim \text{Poisson}(\lambda)\), give \(E[X]\).",
        r"\(E[X] = \lambda\).",
    ),
    SeedCard(
        "univariate",
        "discrete_dists",
        "medium",
        r"For \(X \sim \text{Poisson}(\lambda)\), give \(\mathrm{Var}(X)\).",
        r"\(\mathrm{Var}(X) = \lambda\).",
    ),
    SeedCard(
        "univariate",
        "discrete_dists",
        "medium",
        "For \\(X \\sim \\text{Poisson}(3)\\), find \\(P(X = 0)\\).",
        "The Poisson pmf is \\(P(X=k) = \\dfrac{e^{-\\lambda}\\lambda^{k}}{k!}\\). "
        "At \\(k=0\\), \\[ P(X=0) = e^{-3}\\,\\frac{3^{0}}{0!} = e^{-3} "
        "\\approx 0.0498. \\]",
        kind=KIND_NUMERIC,
        answer="0.0498",
    ),
    SeedCard(
        "univariate",
        "continuous_dists",
        "easy",
        r"For \(X \sim \text{Exponential}\) with rate \(\lambda\), give \(E[X]\).",
        r"\(E[X] = \dfrac{1}{\lambda}\).",
    ),
    SeedCard(
        "univariate",
        "continuous_dists",
        "easy",
        r"For \(X \sim \text{Exponential}\) with rate \(\lambda\), give \(\mathrm{Var}(X)\).",
        r"\(\mathrm{Var}(X) = \dfrac{1}{\lambda^2}\).",
    ),
    SeedCard(
        "univariate",
        "continuous_dists",
        "medium",
        r"For \(X \sim \text{Uniform}(a, b)\), give \(E[X]\).",
        r"\(E[X] = \dfrac{a + b}{2}\).",
    ),
    SeedCard(
        "univariate",
        "continuous_dists",
        "medium",
        r"For \(X \sim \text{Uniform}(a, b)\), give \(\mathrm{Var}(X)\).",
        r"\(\mathrm{Var}(X) = \dfrac{(b - a)^2}{12}\).",
    ),
    SeedCard(
        "univariate",
        "continuous_dists",
        "medium",
        r"\(X \sim \text{Uniform}(0, 1)\) and \(Y = -\ln(X)\). Identify the distribution of \(Y\).",
        r"\(Y \sim \text{Exponential}(1)\): \(F_Y(y) = 1 - e^{-y}\) for \(y > 0\).",
        kind=KIND_NUMERIC,
        answer="Exponential(1)",
    ),
    SeedCard(
        "univariate",
        "insurance_apps",
        "easy",
        r"Loss \(X\) with an ordinary deductible \(d\): write the payment per loss.",
        r"\(\text{Payment} = (X - d)_+ = \max(X - d,\ 0)\).",
    ),
    SeedCard(
        "univariate",
        "insurance_apps",
        "medium",
        r"Loss \(X\) with deductible \(d\) and maximum covered loss \(u\): payment per loss?",
        r"\(\text{Payment} = \min(X, u) - \min(X, d)\).",
    ),
    # --- Multivariate Random Variables ---
    SeedCard(
        "multivariate",
        "joint_distributions",
        "easy",
        r"For a joint density \(f(x, y)\), how do you get \(P\big((X, Y) \in A\big)\)?",
        r"Integrate over the region: \(P\big((X,Y)\in A\big) = \displaystyle\iint_A f(x, y)\,dx\,dy\).",
    ),
    SeedCard(
        "multivariate",
        "joint_distributions",
        "medium",
        r"State the condition for \(X\) and \(Y\) to be independent via the joint density.",
        r"\(f(x, y) = f_X(x)\,f_Y(y)\) for all \(x, y\).",
    ),
    SeedCard(
        "multivariate",
        "marginal_conditional",
        "easy",
        r"Given joint density \(f(x, y)\), give the marginal density \(f_X(x)\).",
        r"\(f_X(x) = \displaystyle\int_{-\infty}^{\infty} f(x, y)\,dy\).",
    ),
    SeedCard(
        "multivariate",
        "marginal_conditional",
        "medium",
        r"Give the conditional density \(f_{Y \mid X}(y \mid x)\).",
        r"\(f_{Y \mid X}(y \mid x) = \dfrac{f(x, y)}{f_X(x)}\), for \(f_X(x) > 0\).",
    ),
    SeedCard(
        "multivariate",
        "joint_moments",
        "medium",
        r"For a joint density \(f(x, y)\), give \(E[g(X, Y)]\).",
        r"\(E[g(X, Y)] = \displaystyle\iint g(x, y)\,f(x, y)\,dx\,dy\).",
    ),
    SeedCard(
        "multivariate",
        "joint_moments",
        "medium",
        r"State the double-expectation (tower) rule for \(E[X]\).",
        r"\(E[X] = E\big[\,E[X \mid Y]\,\big]\).",
    ),
    SeedCard(
        "multivariate",
        "covariance_correlation",
        "easy",
        r"Define \(\mathrm{Cov}(X, Y)\) in terms of expectations.",
        r"\(\mathrm{Cov}(X, Y) = E[XY] - E[X]\,E[Y]\).",
    ),
    SeedCard(
        "multivariate",
        "covariance_correlation",
        "medium",
        r"Define the correlation coefficient \(\rho(X, Y)\).",
        r"\(\rho = \dfrac{\mathrm{Cov}(X, Y)}{\mathrm{SD}(X)\,\mathrm{SD}(Y)}\).",
    ),
    SeedCard(
        "multivariate",
        "covariance_correlation",
        "easy",
        r"If \(X\) and \(Y\) are independent, what is \(\mathrm{Cov}(X, Y)\)?",
        r"\(\mathrm{Cov}(X, Y) = 0\) (the converse need not hold).",
    ),
    SeedCard(
        "multivariate",
        "order_statistics",
        "medium",
        r"For iid \(X_1, \dots, X_n\) with cdf \(F\), give the cdf of the maximum \(X_{(n)}\).",
        r"\(P(X_{(n)} \le x) = [F(x)]^n\).",
    ),
    SeedCard(
        "multivariate",
        "order_statistics",
        "medium",
        r"For iid \(X_1, \dots, X_n\) with cdf \(F\), give the cdf of the minimum \(X_{(1)}\).",
        r"\(P(X_{(1)} \le x) = 1 - [1 - F(x)]^n\).",
    ),
    SeedCard(
        "multivariate",
        "linear_combinations",
        "medium",
        r"Give \(\mathrm{Var}(aX + bY)\) in general (including covariance).",
        r"\(a^2\,\mathrm{Var}(X) + b^2\,\mathrm{Var}(Y) + 2ab\,\mathrm{Cov}(X, Y)\).",
    ),
    SeedCard(
        "multivariate",
        "linear_combinations",
        "hard",
        r"For independent \(X\) and \(Y\), give \(\mathrm{Var}(aX + bY)\).",
        r"\(a^2\,\mathrm{Var}(X) + b^2\,\mathrm{Var}(Y)\).",
    ),
    SeedCard(
        "multivariate",
        "clt",
        "medium",
        r"State the Central Limit Theorem for the sample mean \(\bar{X}\) of \(n\) iid variables.",
        r"For large \(n\), \(\bar{X}\) is approximately \(\text{Normal}\!\left(\mu,\ \dfrac{\sigma^2}{n}\right)\).",
    ),
    SeedCard(
        "multivariate",
        "clt",
        "hard",
        "\\(n = 100\\) i.i.d. values with \\(\\mu = 50\\), \\(\\sigma = 10\\). "
        "Approximate \\(P(\\bar{X} > 52)\\).",
        "By the CLT, \\(\\bar{X} \\approx \\mathcal{N}\\!\\left(\\mu, "
        "\\sigma^{2}/n\\right)\\), so the standard error is "
        "\\(\\sigma/\\sqrt{n} = 10/\\sqrt{100} = 1\\). Standardizing, "
        "\\[ Z = \\frac{52 - 50}{1} = 2, \\qquad "
        "P(\\bar{X} > 52) = P(Z > 2) \\approx 0.0228. \\]",
        kind=KIND_NUMERIC,
        answer="0.0228",
    ),
    # =====================================================================
    # Complete fact coverage: the core memorizable facts for Exam P. Recall
    # (flashcard) cards for every formula/definition/distribution a student is
    # expected to know cold. Standard results, original wording (no exam items).
    # =====================================================================
    # --- General Probability: laws & counting ---
    SeedCard(
        "general",
        "sets_axioms",
        "easy",
        "State the complement rule.",
        r"\(P(A^c) = 1 - P(A)\). Also \(P(\varnothing) = 0\).",
    ),
    SeedCard(
        "general",
        "sets_axioms",
        "medium",
        "State De Morgan's laws for two events.",
        r"\((A \cup B)^c = A^c \cap B^c\); \((A \cap B)^c = A^c \cup B^c\).",
    ),
    SeedCard(
        "general",
        "sets_axioms",
        "medium",
        r"State inclusion-exclusion for three events \(P(A \cup B \cup C)\).",
        r"\(P(A)+P(B)+P(C) - P(A\cap B) - P(A\cap C) - P(B\cap C) + P(A\cap B\cap C)\).",
    ),
    SeedCard(
        "general",
        "combinatorics",
        "easy",
        r"Give the permutation count of \(k\) items from \(n\) (order matters).",
        r"\(P(n,k) = \dfrac{n!}{(n - k)!}\).",
    ),
    SeedCard(
        "general",
        "combinatorics",
        "easy",
        r"Give the combination count of \(k\) items from \(n\) (order does not matter).",
        r"\(\binom{n}{k} = \dfrac{n!}{k!\,(n - k)!}\).",
    ),
    SeedCard(
        "general",
        "combinatorics",
        "medium",
        r"Give the multinomial count of arrangements of \(n\) items in groups of "
        r"sizes \(n_1, \dots, n_k\).",
        r"\(\dfrac{n!}{n_1!\,n_2!\cdots n_k!}\).",
    ),
    SeedCard(
        "general",
        "independence",
        "medium",
        "Give the conditional-probability characterization of independence.",
        r"\(A\) and \(B\) are independent iff \(P(A \mid B) = P(A)\) "
        r"(equivalently \(P(B \mid A) = P(B)\)).",
    ),
    SeedCard(
        "general",
        "independence",
        "medium",
        r"If \(A\) and \(B\) are independent, are \(A\) and \(B^c\) independent?",
        r"Yes. Independence is preserved under complements "
        r"(\(A \cap B^c\), \(A^c \cap B\), \(A^c \cap B^c\)).",
    ),
    SeedCard(
        "general",
        "add_mult_rules",
        "easy",
        r"For mutually exclusive \(A\) and \(B\), give \(P(A \cup B)\).",
        r"\(P(A \cup B) = P(A) + P(B)\), since \(P(A \cap B) = 0\).",
    ),
    SeedCard(
        "general",
        "conditional",
        "medium",
        r"State the law of total probability for a partition \(A_1, \dots, A_n\).",
        r"\(P(B) = \sum_i P(B \mid A_i)\,P(A_i)\).",
    ),
    SeedCard(
        "general",
        "bayes",
        "medium",
        r"State Bayes' theorem with a partition \(A_1, \dots, A_n\) (denominator expanded).",
        r"\(P(A_j \mid B) = \dfrac{P(B \mid A_j)\,P(A_j)}{\sum_i P(B \mid A_i)\,P(A_i)}\).",
    ),
    # --- Univariate: random variables, moments, MGF ---
    SeedCard(
        "univariate",
        "rv_basics",
        "easy",
        r"Give the two properties of a probability mass function \(p(x)\).",
        r"\(0 \le p(x) \le 1\) for all \(x\), and \(\sum_x p(x) = 1\) over the support.",
    ),
    SeedCard(
        "univariate",
        "rv_basics",
        "easy",
        r"Give the two properties of a probability density function \(f(x)\).",
        r"\(f(x) \ge 0\) for all \(x\), and \(\displaystyle\int f(x)\,dx = 1\) over the support.",
    ),
    SeedCard(
        "univariate",
        "rv_basics",
        "medium",
        r"List the defining properties of a CDF \(F(x)\).",
        r"Non-decreasing, right-continuous, \(F(-\infty) = 0\), \(F(+\infty) = 1\).",
    ),
    SeedCard(
        "univariate",
        "rv_basics",
        "easy",
        r"Define the survival function \(S(x)\).",
        r"\(S(x) = P(X > x) = 1 - F(x)\).",
    ),
    SeedCard(
        "univariate",
        "rv_basics",
        "easy",
        r"For a continuous \(X\), give \(P(a < X \le b)\) from the CDF.",
        r"\(P(a < X \le b) = F(b) - F(a)\).",
    ),
    SeedCard(
        "univariate",
        "expectation",
        "easy",
        r"Define \(E[X]\) for a discrete \(X\) with pmf \(p\).",
        r"\(E[X] = \sum_x x\,p(x)\) over the support.",
    ),
    SeedCard(
        "univariate",
        "expectation",
        "medium",
        r"State the law of the unconscious statistician (LOTUS) for \(E[g(X)]\).",
        r"Continuous: \(\displaystyle\int g(x) f(x)\,dx\). Discrete: \(\sum_x g(x) p(x)\).",
    ),
    SeedCard(
        "univariate",
        "expectation",
        "easy",
        r"Give \(E[aX + b]\) (linearity of expectation).",
        r"\(E[aX + b] = a\,E[X] + b\).",
    ),
    SeedCard(
        "univariate",
        "expectation",
        "medium",
        r"For a non-negative \(X\), give \(E[X]\) via the survival function.",
        r"\(E[X] = \displaystyle\int_0^{\infty} S(x)\,dx = \int_0^{\infty} [1 - F(x)]\,dx\).",
    ),
    SeedCard(
        "univariate",
        "expectation",
        "medium",
        r"Define the moment generating function \(M_X(t)\).",
        r"\(M_X(t) = E[e^{tX}]\).",
    ),
    SeedCard(
        "univariate",
        "expectation",
        "medium",
        r"How do you get moments from the MGF \(M_X(t)\)?",
        r"\(M'(0) = E[X]\), \(M''(0) = E[X^2]\), and the \(k\)-th derivative at \(0\) is \(E[X^k]\).",
    ),
    SeedCard(
        "univariate",
        "variance",
        "easy",
        r"Define the standard deviation of \(X\).",
        r"\(\mathrm{SD}(X) = \sqrt{\mathrm{Var}(X)}\).",
    ),
    SeedCard(
        "univariate",
        "variance",
        "easy",
        r"Give \(\mathrm{Var}(aX + b)\).",
        r"\(\mathrm{Var}(aX + b) = a^2\,\mathrm{Var}(X)\) (the constant \(b\) does not affect variance).",
    ),
    # --- Univariate: discrete distributions (pmf, mean, variance) ---
    SeedCard(
        "univariate",
        "discrete_dists",
        "easy",
        r"For \(X \sim \text{Bernoulli}(p)\), give the pmf.",
        r"\(p(1) = p,\ p(0) = 1 - p\).",
    ),
    SeedCard(
        "univariate",
        "discrete_dists",
        "easy",
        r"For \(X \sim \text{Bernoulli}(p)\), give \(E[X]\).",
        r"\(E[X] = p\).",
    ),
    SeedCard(
        "univariate",
        "discrete_dists",
        "easy",
        r"For \(X \sim \text{Bernoulli}(p)\), give \(\mathrm{Var}(X)\).",
        r"\(\mathrm{Var}(X) = p(1 - p)\).",
    ),
    SeedCard(
        "univariate",
        "discrete_dists",
        "medium",
        r"For \(X \sim \text{Binomial}(n, p)\), give the pmf \(p(k)\).",
        r"\(p(k) = \binom{n}{k} p^k (1 - p)^{n - k}\), for \(k = 0, 1, \dots, n\).",
    ),
    SeedCard(
        "univariate",
        "discrete_dists",
        "medium",
        r"For \(X \sim \text{Geometric}(p)\) (trials until the first success, "
        r"\(k = 1, 2, \dots\)), give the pmf.",
        r"\(p(k) = (1 - p)^{k - 1} p\).",
    ),
    SeedCard(
        "univariate",
        "discrete_dists",
        "medium",
        r"For \(X \sim \text{Geometric}(p)\) (trials until the first success, "
        r"\(k = 1, 2, \dots\)), give \(E[X]\).",
        r"\(E[X] = \dfrac{1}{p}\).",
    ),
    SeedCard(
        "univariate",
        "discrete_dists",
        "medium",
        r"For \(X \sim \text{Geometric}(p)\) (trials until the first success, "
        r"\(k = 1, 2, \dots\)), give \(\mathrm{Var}(X)\).",
        r"\(\mathrm{Var}(X) = \dfrac{1 - p}{p^2}\).",
    ),
    SeedCard(
        "univariate",
        "discrete_dists",
        "medium",
        r"For \(X \sim \text{Negative Binomial}(r, p)\) (trials until the \(r\)-th "
        r"success), give \(E[X]\).",
        r"\(E[X] = \dfrac{r}{p}\).",
    ),
    SeedCard(
        "univariate",
        "discrete_dists",
        "medium",
        r"For \(X \sim \text{Negative Binomial}(r, p)\) (trials until the \(r\)-th "
        r"success), give \(\mathrm{Var}(X)\).",
        r"\(\mathrm{Var}(X) = \dfrac{r(1 - p)}{p^2}\).",
    ),
    SeedCard(
        "univariate",
        "discrete_dists",
        "hard",
        r"For \(X \sim \text{Hypergeometric}\) (\(n\) draws without replacement from "
        r"\(N\) items, \(K\) successes), give \(E[X]\).",
        r"\(E[X] = \dfrac{nK}{N}\).",
    ),
    SeedCard(
        "univariate",
        "discrete_dists",
        "hard",
        r"For \(X \sim \text{Hypergeometric}\) (\(n\) draws without replacement from "
        r"\(N\) items, \(K\) successes), give \(\mathrm{Var}(X)\).",
        r"\(\mathrm{Var}(X) = n\,\dfrac{K}{N}\left(1 - \dfrac{K}{N}\right)\dfrac{N - n}{N - 1}\) "
        r"(finite-population correction).",
    ),
    SeedCard(
        "univariate",
        "discrete_dists",
        "medium",
        r"For \(X \sim \text{Poisson}(\lambda)\), give the pmf \(p(k)\).",
        r"\(p(k) = \dfrac{e^{-\lambda} \lambda^k}{k!}\), for \(k = 0, 1, 2, \dots\)",
    ),
    SeedCard(
        "univariate",
        "discrete_dists",
        "medium",
        r"For \(X\) discrete uniform on \(\{1, \dots, n\}\), give \(E[X]\).",
        r"\(E[X] = \dfrac{n + 1}{2}\).",
    ),
    SeedCard(
        "univariate",
        "discrete_dists",
        "medium",
        r"For \(X\) discrete uniform on \(\{1, \dots, n\}\), give \(\mathrm{Var}(X)\).",
        r"\(\mathrm{Var}(X) = \dfrac{n^2 - 1}{12}\).",
    ),
    # --- Univariate: continuous distributions ---
    SeedCard(
        "univariate",
        "continuous_dists",
        "easy",
        "For X ~ Uniform(a, b), give the pdf f(x).",
        "f(x) = 1 / (b - a) for a <= x <= b, and 0 otherwise.",
    ),
    SeedCard(
        "univariate",
        "continuous_dists",
        "medium",
        "For X ~ Exponential(rate lambda), give the pdf.",
        "f(x) = lambda e^(-lambda x), for x >= 0.",
    ),
    SeedCard(
        "univariate",
        "continuous_dists",
        "medium",
        "For X ~ Exponential(rate lambda), give the cdf.",
        "F(x) = 1 - e^(-lambda x), for x >= 0.",
    ),
    SeedCard(
        "univariate",
        "continuous_dists",
        "easy",
        "For X ~ Normal(mu, sigma^2), give E[X].",
        "E[X] = mu.",
    ),
    SeedCard(
        "univariate",
        "continuous_dists",
        "easy",
        "For X ~ Normal(mu, sigma^2), give Var(X).",
        "Var(X) = sigma^2.",
    ),
    SeedCard(
        "univariate",
        "continuous_dists",
        "easy",
        "For X ~ Normal(mu, sigma^2), how do you standardize X?",
        "Z = (X - mu) / sigma ~ Normal(0, 1).",
    ),
    SeedCard(
        "univariate",
        "continuous_dists",
        "medium",
        "For X ~ Gamma(shape alpha, scale theta), give E[X].",
        "E[X] = alpha theta.",
    ),
    SeedCard(
        "univariate",
        "continuous_dists",
        "medium",
        "For X ~ Gamma(shape alpha, scale theta), give Var(X).",
        "Var(X) = alpha theta^2. "
        "(Exponential with mean theta is Gamma(1, theta).)",
    ),
    # --- Univariate: insurance / coverage modifications ---
    SeedCard(
        "univariate",
        "insurance_apps",
        "medium",
        "For loss X with ordinary deductible d, give the expected payment per "
        "loss E[(X - d)_+].",
        "E[(X - d)_+] = integral from d to infinity of S(x) dx = "
        "integral from d to infinity of [1 - F(x)] dx.",
    ),
    SeedCard(
        "univariate",
        "insurance_apps",
        "hard",
        "Relate the expected payment PER PAYMENT to the expected payment PER LOSS "
        "for a deductible d.",
        "E[payment | payment > 0] = E[(X - d)_+] / P(X > d) = E[(X - d)_+] / S(d).",
    ),
    # --- Multivariate: joint behaviour, conditioning, moments ---
    SeedCard(
        "multivariate",
        "joint_distributions",
        "easy",
        "Give the normalization condition for a joint pmf and a joint pdf.",
        "Discrete: sum over all (x, y) of p(x, y) = 1. "
        "Continuous: double integral of f(x, y) = 1.",
    ),
    SeedCard(
        "multivariate",
        "joint_moments",
        "medium",
        "If X and Y are independent, give E[XY].",
        "E[XY] = E[X] E[Y] (holds whenever X and Y are independent).",
    ),
    SeedCard(
        "multivariate",
        "joint_moments",
        "hard",
        "State the law of total variance.",
        "Var(X) = E[ Var(X | Y) ] + Var( E[X | Y] ).",
    ),
    SeedCard(
        "multivariate",
        "covariance_correlation",
        "easy",
        "What is Cov(X, X)?",
        "Cov(X, X) = Var(X).",
    ),
    SeedCard(
        "multivariate",
        "covariance_correlation",
        "medium",
        "Give the bilinearity rule Cov(aX + b, cY + d).",
        "Cov(aX + b, cY + d) = a c Cov(X, Y) (added constants drop out).",
    ),
    SeedCard(
        "multivariate",
        "covariance_correlation",
        "easy",
        "What is the range of the correlation coefficient rho?",
        "-1 <= rho <= 1.",
    ),
    SeedCard(
        "multivariate",
        "covariance_correlation",
        "medium",
        "Give Var(X + Y) including covariance.",
        "Var(X + Y) = Var(X) + Var(Y) + 2 Cov(X, Y).",
    ),
    SeedCard(
        "multivariate",
        "order_statistics",
        "hard",
        "For independent X_i ~ Exponential(rate lambda_i), what is the "
        "distribution of the minimum?",
        "min(X_i) ~ Exponential with rate = sum of the lambda_i.",
    ),
    # --- Multivariate: linear combinations & sums of independents ---
    SeedCard(
        "multivariate",
        "linear_combinations",
        "easy",
        "Give E[aX + bY].",
        "E[aX + bY] = a E[X] + b E[Y] (always, independent or not).",
    ),
    SeedCard(
        "multivariate",
        "linear_combinations",
        "medium",
        "Give Var(X - Y) including covariance.",
        "Var(X - Y) = Var(X) + Var(Y) - 2 Cov(X, Y).",
    ),
    SeedCard(
        "multivariate",
        "linear_combinations",
        "medium",
        "The sum of independent normals is what distribution?",
        "Normal: X + Y ~ Normal(mu_X + mu_Y, sigma_X^2 + sigma_Y^2).",
    ),
    SeedCard(
        "multivariate",
        "linear_combinations",
        "medium",
        "The sum of independent Poissons is what distribution?",
        "Poisson: X + Y ~ Poisson(lambda_X + lambda_Y).",
    ),
    SeedCard(
        "multivariate",
        "linear_combinations",
        "hard",
        "For INDEPENDENT X and Y, give the MGF of the sum X + Y.",
        "M_(X+Y)(t) = M_X(t) M_Y(t) (MGF of a sum of independents is the product).",
    ),
    SeedCard(
        "multivariate",
        "marginal_conditional",
        "easy",
        "For a discrete joint pmf p(x, y), give the marginal pmf p_X(x).",
        "p_X(x) = sum over y of p(x, y).",
    ),
    SeedCard(
        "multivariate",
        "marginal_conditional",
        "medium",
        "When X and Y are independent, how does the conditional relate to the "
        "marginal?",
        "f_(Y|X)(y | x) = f_Y(y): the conditional equals the marginal, so X "
        "carries no information about Y.",
    ),
    SeedCard(
        "multivariate",
        "clt",
        "medium",
        "State the CLT for the SUM S_n = X_1 + ... + X_n of n iid variables.",
        "For large n, S_n is approximately Normal(n mu, n sigma^2).",
    ),
    SeedCard(
        "multivariate",
        "clt",
        "medium",
        "When approximating a discrete sum (e.g. a Binomial count) by the normal, "
        "what adjustment improves accuracy?",
        "The continuity correction: shift the boundary by 0.5, e.g. "
        "P(X <= k) ≈ P(Z <= (k + 0.5 - mu)/sigma).",
    ),
]


# Comprehensive "memorize-facts" deck: the formulas Exam P expects you to KNOW
# cold (the distribution table, the moment/variance identities, the multivariate
# rules). Appended so the starter deck above stays a gentle on-ramp while these
# fill the recall gaps. All are flashcards (recall); math is LaTeX, which Anki
# renders (\( \) inline, \[ \] display). Tags/decks come from the same subtopic
# ids, so coverage and the mastery scheduler treat them like any other card.
SEED_CARDS.extend(
    [
        # --- General Probability: sets & axioms ---
        SeedCard(
            "general", "sets_axioms", "medium",
            "State Kolmogorov's three axioms of probability.",
            r"1) \(P(A) \ge 0\) for every event \(A\).<br>"
            r"2) \(P(S) = 1\) for the sample space \(S\).<br>"
            r"3) For mutually exclusive \(A_1, A_2, \dots\), "
            r"\(P\!\left(\bigcup_i A_i\right) = \sum_i P(A_i)\).",
        ),
        SeedCard(
            "general", "sets_axioms", "easy",
            "State the complement rule and De Morgan's laws.",
            r"Complement: \(P(A^c) = 1 - P(A)\).<br>"
            r"De Morgan: \((A \cup B)^c = A^c \cap B^c\) and "
            r"\((A \cap B)^c = A^c \cup B^c\).",
        ),
        SeedCard(
            "general", "sets_axioms", "medium",
            "State inclusion-exclusion for two and three events.",
            r"\(P(A \cup B) = P(A) + P(B) - P(A \cap B)\).<br>"
            r"\(P(A \cup B \cup C) = P(A)+P(B)+P(C) - P(AB) - P(AC) - P(BC) + P(ABC)\).",
        ),
        # --- General Probability: combinatorics ---
        SeedCard(
            "general", "combinatorics", "medium",
            "Permutations vs. combinations of k chosen from n.",
            r"Order matters (permutations): \(P(n,k) = \dfrac{n!}{(n-k)!}\).<br>"
            r"Order doesn't (combinations): \(\binom{n}{k} = \dfrac{n!}{k!\,(n-k)!}\).",
        ),
        SeedCard(
            "general", "combinatorics", "medium",
            "State the multinomial coefficient (split n items into groups of "
            "sizes n_1, ..., n_r).",
            r"\(\dbinom{n}{n_1, n_2, \dots, n_r} = \dfrac{n!}{n_1!\,n_2!\cdots n_r!}\), "
            r"with \(n_1 + \cdots + n_r = n\).",
        ),
        # --- General Probability: addition & multiplication rules ---
        SeedCard(
            "general", "add_mult_rules", "easy",
            "State the multiplication (chain) rule for a joint probability.",
            r"\(P(A \cap B) = P(A)\,P(B \mid A) = P(B)\,P(A \mid B)\).",
        ),
        # --- General Probability: conditional probability ---
        SeedCard(
            "general", "conditional", "medium",
            "Define conditional probability and the law of total probability.",
            r"\(P(A \mid B) = \dfrac{P(A \cap B)}{P(B)}\), \(P(B) > 0\).<br>"
            r"For a partition \(B_1, \dots, B_n\): "
            r"\(P(A) = \sum_i P(A \mid B_i)\,P(B_i)\).",
        ),
        # --- General Probability: independence ---
        SeedCard(
            "general", "independence", "medium",
            "When are A and B independent, and how does that differ from "
            "mutually exclusive?",
            r"Independent: \(P(A \cap B) = P(A)\,P(B)\) (so \(P(A \mid B) = P(A)\)).<br>"
            r"Mutually exclusive: \(A \cap B = \emptyset\), so \(P(A \cap B) = 0\). "
            r"Independent events with positive probability are NOT mutually exclusive.",
        ),
        # --- General Probability: Bayes' theorem ---
        SeedCard(
            "general", "bayes", "medium",
            "State Bayes' theorem for a partition of the sample space.",
            r"\(P(B_j \mid A) = \dfrac{P(A \mid B_j)\,P(B_j)}"
            r"{\sum_i P(A \mid B_i)\,P(B_i)}\).",
        ),
        # --- Univariate: random variables, PDFs, CDFs ---
        SeedCard(
            "univariate", "rv_basics", "medium",
            "State the relationship between the pdf f and cdf F of a continuous "
            "random variable.",
            r"\(F(x) = \displaystyle\int_{-\infty}^{x} f(t)\,dt\) and \(f(x) = F'(x)\).<br>"
            r"\(P(a < X \le b) = F(b) - F(a) = \int_a^b f(x)\,dx\).",
        ),
        SeedCard(
            "univariate", "rv_basics", "easy",
            "State the defining properties of a cumulative distribution function "
            "F(x).",
            r"Non-decreasing; right-continuous; "
            r"\(\lim_{x \to -\infty} F(x) = 0\) and \(\lim_{x \to \infty} F(x) = 1\).",
        ),
        # --- Univariate: expectation, moments, MGF ---
        SeedCard(
            "univariate", "expectation", "medium",
            "Define E[X] (discrete and continuous) and the law of the "
            "unconscious statistician (LOTUS).",
            r"\(E[X] = \sum_x x\,p(x)\) or \(\displaystyle\int_{-\infty}^{\infty} x f(x)\,dx\).<br>"
            r"LOTUS: \(E[g(X)] = \sum_x g(x)p(x)\) or \(\int g(x) f(x)\,dx\).",
        ),
        SeedCard(
            "univariate", "expectation", "medium",
            "State the survival-function (tail) formula for the mean of a "
            "nonnegative random variable.",
            r"For \(X \ge 0\): \(E[X] = \displaystyle\int_0^\infty \big(1 - F(x)\big)\,dx "
            r"= \int_0^\infty S(x)\,dx\), where \(S(x) = P(X > x)\).",
        ),
        SeedCard(
            "univariate", "expectation", "hard",
            "Define the moment generating function and how to recover moments "
            "from it.",
            r"\(M_X(t) = E[e^{tX}]\). Then \(M_X'(0) = E[X]\), \(M_X''(0) = E[X^2]\), "
            r"and \(M_X^{(n)}(0) = E[X^n]\).",
        ),
        SeedCard(
            "univariate", "expectation", "hard",
            "State the MGF rules for a linear transform and for a sum of "
            "independent variables.",
            r"\(M_{aX+b}(t) = e^{bt} M_X(at)\); if \(X, Y\) independent, "
            r"\(M_{X+Y}(t) = M_X(t)\,M_Y(t)\). The MGF (when it exists) uniquely "
            r"determines the distribution.",
        ),
        # --- Univariate: variance, SD, CV ---
        SeedCard(
            "univariate", "variance", "easy",
            "Define variance and give its computational formula; how does a "
            "linear transform change it?",
            r"\(\mathrm{Var}(X) = E[(X-\mu)^2] = E[X^2] - (E[X])^2\); "
            r"\(\mathrm{SD} = \sqrt{\mathrm{Var}(X)}\).<br>"
            r"\(\mathrm{Var}(aX + b) = a^2\,\mathrm{Var}(X)\).",
        ),
        SeedCard(
            "univariate", "variance", "medium",
            "State Chebyshev's inequality and define the coefficient of "
            "variation.",
            r"\(P(|X - \mu| \ge k\sigma) \le \dfrac{1}{k^2}\) for any \(k > 0\).<br>"
            r"Coefficient of variation \(= \dfrac{\sigma}{\mu}\).",
        ),
        # --- Univariate: common discrete distributions (the table) ---
        SeedCard(
            "univariate", "discrete_dists", "medium",
            "State the pmf of Bernoulli(p).",
            r"\(P(X=1)=p,\ P(X=0)=1-p\).",
        ),
        SeedCard(
            "univariate", "discrete_dists", "medium",
            "State the mean of Bernoulli(p).",
            r"\(E[X]=p\).",
        ),
        SeedCard(
            "univariate", "discrete_dists", "medium",
            "State the variance of Bernoulli(p).",
            r"\(\mathrm{Var}(X)=p(1-p)\).",
        ),
        SeedCard(
            "univariate", "discrete_dists", "medium",
            "State the MGF of Bernoulli(p).",
            r"\(M(t)=1-p+pe^{t}\).",
        ),
        SeedCard(
            "univariate", "discrete_dists", "medium",
            "State the pmf of Binomial(n, p).",
            r"\(P(X=k)=\binom{n}{k}p^{k}(1-p)^{n-k}\), \(k=0,\dots,n\).",
        ),
        SeedCard(
            "univariate", "discrete_dists", "medium",
            "State the mean of Binomial(n, p).",
            r"\(E[X]=np\).",
        ),
        SeedCard(
            "univariate", "discrete_dists", "medium",
            "State the variance of Binomial(n, p).",
            r"\(\mathrm{Var}(X)=np(1-p)\).",
        ),
        SeedCard(
            "univariate", "discrete_dists", "medium",
            "State the MGF of Binomial(n, p).",
            r"\(M(t)=(1-p+pe^{t})^{n}\).",
        ),
        SeedCard(
            "univariate", "discrete_dists", "medium",
            "State the pmf of Geometric(p) (number of trials up to and including "
            "the first success).",
            r"\(P(X=k)=(1-p)^{k-1}p\), \(k=1,2,\dots\).",
        ),
        SeedCard(
            "univariate", "discrete_dists", "medium",
            "State the mean of Geometric(p) (number of trials up to and including "
            "the first success).",
            r"\(E[X]=\dfrac{1}{p}\).",
        ),
        SeedCard(
            "univariate", "discrete_dists", "medium",
            "State the variance of Geometric(p) (number of trials up to and "
            "including the first success).",
            r"\(\mathrm{Var}(X)=\dfrac{1-p}{p^{2}}\). (It is memoryless.)",
        ),
        SeedCard(
            "univariate", "discrete_dists", "hard",
            "State the pmf of Negative Binomial(r, p) (trials until the r-th "
            "success).",
            r"\(P(X=k)=\binom{k-1}{r-1}p^{r}(1-p)^{k-r}\), \(k=r,r+1,\dots\).",
        ),
        SeedCard(
            "univariate", "discrete_dists", "hard",
            "State the mean of Negative Binomial(r, p) (trials until the r-th "
            "success).",
            r"\(E[X]=\dfrac{r}{p}\).",
        ),
        SeedCard(
            "univariate", "discrete_dists", "hard",
            "State the variance of Negative Binomial(r, p) (trials until the r-th "
            "success).",
            r"\(\mathrm{Var}(X)=\dfrac{r(1-p)}{p^{2}}\).",
        ),
        SeedCard(
            "univariate", "discrete_dists", "medium",
            "State the pmf of Poisson(lambda).",
            r"\(P(X=k)=\dfrac{e^{-\lambda}\lambda^{k}}{k!}\), \(k=0,1,\dots\).",
        ),
        SeedCard(
            "univariate", "discrete_dists", "medium",
            "State the mean of Poisson(lambda).",
            r"\(E[X]=\lambda\).",
        ),
        SeedCard(
            "univariate", "discrete_dists", "medium",
            "State the variance of Poisson(lambda).",
            r"\(\mathrm{Var}(X)=\lambda\).",
        ),
        SeedCard(
            "univariate", "discrete_dists", "medium",
            "State the MGF of Poisson(lambda).",
            r"\(M(t)=e^{\lambda(e^{t}-1)}\).",
        ),
        SeedCard(
            "univariate", "discrete_dists", "hard",
            "State the pmf of the Hypergeometric distribution (n draws without "
            "replacement from N items, K of them successes).",
            r"\(P(X=k)=\dfrac{\binom{K}{k}\binom{N-K}{n-k}}{\binom{N}{n}}\).",
        ),
        SeedCard(
            "univariate", "discrete_dists", "hard",
            "State the mean of the Hypergeometric distribution (n draws without "
            "replacement from N items, K of them successes).",
            r"\(E[X]=n\dfrac{K}{N}\).",
        ),
        SeedCard(
            "univariate", "discrete_dists", "hard",
            "State the variance of the Hypergeometric distribution (n draws "
            "without replacement from N items, K of them successes).",
            r"\(\mathrm{Var}(X)=n\dfrac{K}{N}\Big(1-\dfrac{K}{N}\Big)\dfrac{N-n}{N-1}\).",
        ),
        SeedCard(
            "univariate", "discrete_dists", "medium",
            "In a Poisson process with rate lambda, what is the distribution of "
            "the number of events in an interval of length t?",
            r"The number of events in an interval of length \(t\) is "
            r"\(\mathrm{Poisson}(\lambda t)\).",
        ),
        SeedCard(
            "univariate", "discrete_dists", "medium",
            "In a Poisson process with rate lambda, what is the distribution of "
            "the interarrival (waiting) times between consecutive events?",
            r"The interarrival times are \(\mathrm{Exponential}\) with mean "
            r"\(1/\lambda\) (rate \(\lambda\)).",
        ),
        # --- Univariate: common continuous distributions (the table) ---
        SeedCard(
            "univariate", "continuous_dists", "medium",
            "State the pdf of a continuous Uniform(a, b).",
            r"\(f(x)=\dfrac{1}{b-a}\), \(a<x<b\).",
        ),
        SeedCard(
            "univariate", "continuous_dists", "medium",
            "State the mean of a continuous Uniform(a, b).",
            r"\(E[X]=\dfrac{a+b}{2}\).",
        ),
        SeedCard(
            "univariate", "continuous_dists", "medium",
            "State the variance of a continuous Uniform(a, b).",
            r"\(\mathrm{Var}(X)=\dfrac{(b-a)^{2}}{12}\).",
        ),
        SeedCard(
            "univariate", "continuous_dists", "medium",
            "State the pdf of an Exponential with mean theta.",
            r"\(f(x)=\dfrac{1}{\theta}e^{-x/\theta}\), \(x>0\).",
        ),
        SeedCard(
            "univariate", "continuous_dists", "medium",
            "State the cdf of an Exponential with mean theta.",
            r"\(F(x)=1-e^{-x/\theta}\), \(x>0\).",
        ),
        SeedCard(
            "univariate", "continuous_dists", "medium",
            "State the mean of an Exponential with mean theta.",
            r"\(E[X]=\theta\).",
        ),
        SeedCard(
            "univariate", "continuous_dists", "medium",
            "State the variance of an Exponential with mean theta.",
            r"\(\mathrm{Var}(X)=\theta^{2}\).",
        ),
        SeedCard(
            "univariate", "continuous_dists", "medium",
            "State the MGF of an Exponential with mean theta.",
            r"\(M(t)=\dfrac{1}{1-\theta t}\) for \(t<1/\theta\).",
        ),
        SeedCard(
            "univariate", "continuous_dists", "medium",
            "State the memoryless property of the exponential distribution.",
            r"\(P(X > s+t \mid X > s) = P(X > t)\) for all \(s,t \ge 0\). "
            r"The exponential is the only continuous distribution with this property.",
        ),
        SeedCard(
            "univariate", "continuous_dists", "hard",
            "State the pdf of a Gamma with shape alpha and scale theta.",
            r"\(f(x)=\dfrac{x^{\alpha-1}e^{-x/\theta}}{\Gamma(\alpha)\,\theta^{\alpha}}\), "
            r"\(x>0\).",
        ),
        SeedCard(
            "univariate", "continuous_dists", "hard",
            "State the mean of a Gamma with shape alpha and scale theta.",
            r"\(E[X]=\alpha\theta\).",
        ),
        SeedCard(
            "univariate", "continuous_dists", "hard",
            "State the variance of a Gamma with shape alpha and scale theta.",
            r"\(\mathrm{Var}(X)=\alpha\theta^{2}\).",
        ),
        SeedCard(
            "univariate", "continuous_dists", "hard",
            "State the MGF of a Gamma with shape alpha and scale theta.",
            r"\(M(t)=(1-\theta t)^{-\alpha}\). (\(\alpha=1\) is the exponential; a "
            r"sum of \(\alpha\) iid exponentials.)",
        ),
        SeedCard(
            "univariate", "continuous_dists", "medium",
            "State the pdf of Normal(mu, sigma^2).",
            r"\(f(x)=\dfrac{1}{\sigma\sqrt{2\pi}}\exp\!\Big(-\dfrac{(x-\mu)^2}{2\sigma^2}\Big)\).",
        ),
        SeedCard(
            "univariate", "continuous_dists", "medium",
            "State the mean of Normal(mu, sigma^2).",
            r"\(E[X]=\mu\).",
        ),
        SeedCard(
            "univariate", "continuous_dists", "medium",
            "State the variance of Normal(mu, sigma^2).",
            r"\(\mathrm{Var}(X)=\sigma^{2}\).",
        ),
        SeedCard(
            "univariate", "continuous_dists", "medium",
            "State the MGF of Normal(mu, sigma^2).",
            r"\(M(t)=\exp\!\big(\mu t + \tfrac12\sigma^{2}t^{2}\big)\).",
        ),
        SeedCard(
            "univariate", "continuous_dists", "easy",
            "How do you standardize a normal random variable X ~ Normal(mu, "
            "sigma^2)?",
            r"\(Z=\dfrac{X-\mu}{\sigma}\sim N(0,1)\).",
        ),
        SeedCard(
            "univariate", "continuous_dists", "easy",
            "For X ~ Normal(mu, sigma^2), how do you find the p-th percentile "
            "x_p?",
            r"\(x_p = \mu + z_p\,\sigma\), where \(z_p\) is the standard-normal "
            r"\(p\)-th percentile (\(\Phi(z_p)=p\), from the z-table). The median "
            r"is \(\mu\).",
        ),
        SeedCard(
            "univariate", "continuous_dists", "hard",
            "State the pdf of a Beta(alpha, beta) on (0, 1).",
            r"\(f(x)=\dfrac{\Gamma(\alpha+\beta)}{\Gamma(\alpha)\Gamma(\beta)}"
            r"x^{\alpha-1}(1-x)^{\beta-1}\), \(0<x<1\).",
        ),
        SeedCard(
            "univariate", "continuous_dists", "hard",
            "State the mean of a Beta(alpha, beta) on (0, 1).",
            r"\(E[X]=\dfrac{\alpha}{\alpha+\beta}\).",
        ),
        SeedCard(
            "univariate", "continuous_dists", "hard",
            "State the variance of a Beta(alpha, beta) on (0, 1).",
            r"\(\mathrm{Var}(X)=\dfrac{\alpha\beta}{(\alpha+\beta)^2(\alpha+\beta+1)}\).",
        ),
        # --- Univariate: insurance applications ---
        SeedCard(
            "univariate", "insurance_apps", "hard",
            "Give the expected cost per loss with an ordinary deductible d.",
            r"Payment \(=(X-d)_+=\max(X-d,0)\).<br>"
            r"\(E[(X-d)_+]=\displaystyle\int_d^\infty (x-d)f(x)\,dx "
            r"= \int_d^\infty \big(1-F(x)\big)\,dx\).",
        ),
        SeedCard(
            "univariate", "insurance_apps", "hard",
            "Give the expected payment with a policy limit u (a capped loss), and "
            "with a coinsurance factor alpha.",
            r"\(E[\min(X,u)] = \displaystyle\int_0^u \big(1-F(x)\big)\,dx\).<br>"
            r"With coinsurance \(\alpha\) and deductible \(d\), expected payment "
            r"\(= \alpha\,E[(X-d)_+]\).",
        ),
        # --- Multivariate: joint distributions ---
        SeedCard(
            "multivariate", "joint_distributions", "medium",
            "Define a joint pdf and how to get a probability over a region.",
            r"\(f_{X,Y}(x,y) \ge 0\), \(\iint f = 1\).<br>"
            r"\(P((X,Y) \in A) = \displaystyle\iint_A f_{X,Y}(x,y)\,dx\,dy\).",
        ),
        # --- Multivariate: marginal & conditional ---
        SeedCard(
            "multivariate", "marginal_conditional", "medium",
            "How do you get marginal densities, the conditional density, and "
            "test independence from a joint density?",
            r"\(f_X(x)=\displaystyle\int f_{X,Y}(x,y)\,dy\); "
            r"\(f_{Y\mid X}(y\mid x)=\dfrac{f_{X,Y}(x,y)}{f_X(x)}\).<br>"
            r"Independent \(\iff f_{X,Y}(x,y)=f_X(x)f_Y(y)\) for all \(x,y\).",
        ),
        SeedCard(
            "multivariate", "marginal_conditional", "hard",
            "State the double-expectation (tower) rule and the law of total "
            "variance.",
            r"\(E[Y]=E\big[E[Y\mid X]\big]\).<br>"
            r"\(\mathrm{Var}(Y)=E\big[\mathrm{Var}(Y\mid X)\big]"
            r"+\mathrm{Var}\big(E[Y\mid X]\big)\).",
        ),
        # --- Multivariate: joint moments ---
        SeedCard(
            "multivariate", "joint_moments", "medium",
            "How do you compute E[g(X, Y)] from a joint density?",
            r"\(E[g(X,Y)] = \displaystyle\iint g(x,y)\,f_{X,Y}(x,y)\,dx\,dy\); "
            r"in particular \(E[XY]=\iint xy\,f_{X,Y}\,dx\,dy\).",
        ),
        # --- Multivariate: covariance & correlation ---
        SeedCard(
            "multivariate", "covariance_correlation", "medium",
            "Define covariance and correlation and give the key identities.",
            r"\(\mathrm{Cov}(X,Y)=E[XY]-E[X]E[Y]\); "
            r"\(\rho=\dfrac{\mathrm{Cov}(X,Y)}{\sigma_X\sigma_Y}\in[-1,1]\).<br>"
            r"Independent \(\Rightarrow \mathrm{Cov}=0\) (the converse is false).",
        ),
        SeedCard(
            "multivariate", "covariance_correlation", "hard",
            "State the variance of a sum and the bilinearity of covariance.",
            r"\(\mathrm{Var}(aX+bY)=a^{2}\mathrm{Var}(X)+b^{2}\mathrm{Var}(Y)"
            r"+2ab\,\mathrm{Cov}(X,Y)\).<br>"
            r"\(\mathrm{Cov}(aX+b,\,cY+d)=ac\,\mathrm{Cov}(X,Y)\).",
        ),
        # --- Multivariate: order statistics ---
        SeedCard(
            "multivariate", "order_statistics", "hard",
            "Give the densities of the min and max of n iid variables with cdf F "
            "and pdf f.",
            r"Max: \(F_{(n)}(x)=F(x)^{n}\), \(f_{(n)}(x)=nF(x)^{n-1}f(x)\).<br>"
            r"Min: \(F_{(1)}(x)=1-(1-F(x))^{n}\), "
            r"\(f_{(1)}(x)=n(1-F(x))^{n-1}f(x)\).",
        ),
        SeedCard(
            "multivariate", "order_statistics", "hard",
            "Give the density of the k-th order statistic of n iid variables.",
            r"\(f_{(k)}(x)=\dfrac{n!}{(k-1)!\,(n-k)!}\,"
            r"F(x)^{k-1}\big(1-F(x)\big)^{n-k}f(x)\).",
        ),
        # --- Multivariate: linear combinations ---
        SeedCard(
            "multivariate", "linear_combinations", "medium",
            "Give the mean and variance of a linear combination of random "
            "variables.",
            r"\(E\big[\sum a_i X_i\big]=\sum a_i E[X_i]\).<br>"
            r"\(\mathrm{Var}\big(\sum a_i X_i\big)=\sum a_i^{2}\mathrm{Var}(X_i)"
            r"+2\sum_{i<j}a_i a_j\,\mathrm{Cov}(X_i,X_j)\) "
            r"(covariance terms vanish if independent).",
        ),
        SeedCard(
            "multivariate", "linear_combinations", "hard",
            "State the reproductive properties of sums of independent common "
            "distributions.",
            r"Independent sums: "
            r"\(\sum \mathrm{Poisson}(\lambda_i)=\mathrm{Poisson}(\sum\lambda_i)\); "
            r"\(\sum \mathrm{Normal}(\mu_i,\sigma_i^{2})="
            r"\mathrm{Normal}(\sum\mu_i,\sum\sigma_i^{2})\); "
            r"\(\sum_{1}^{n}\mathrm{Exp}(\theta)=\mathrm{Gamma}(n,\theta)\); "
            r"\(\sum \mathrm{Binomial}(n_i,p)=\mathrm{Binomial}(\sum n_i,p)\).",
        ),
        # --- Multivariate: central limit theorem ---
        SeedCard(
            "multivariate", "clt", "medium",
            "State the Central Limit Theorem for the sample mean.",
            r"For iid \(X_i\) with mean \(\mu\) and variance \(\sigma^{2}\), for large "
            r"\(n\): \(\bar X_n \approx N\!\Big(\mu,\dfrac{\sigma^{2}}{n}\Big)\), "
            r"equivalently \(\sum X_i \approx N(n\mu,\,n\sigma^{2})\); "
            r"\(Z=\dfrac{\bar X-\mu}{\sigma/\sqrt{n}}\).",
        ),
    ]
)


# Card styling for the typed short-answer notetype. NOTE: the seeded study deck
# no longer uses this — every seeded card is a Basic flip card now. It is kept
# only for the AI-generated *quarantine* cards (``anki.speedrun.ai``), which stay
# exam-style/typed until a human reviews them. Readable left-aligned layout, an
# accent "Solution" block for the worked derivation, and comfortable sizing for
# MathJax (Anki renders \( \) inline and \[ \] display math out of the box).
_SHORT_ANSWER_CSS = """
.card {
    font-family: -apple-system, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
    font-size: 20px;
    color: #1c1c1e;
    background: #f6f7fb;
}
.sa-card { max-width: 640px; margin: 0 auto; text-align: left; line-height: 1.5; }
.sa-q { font-size: 1.1em; font-weight: 600; margin-bottom: 1rem; }
.sa-prompt {
    font-size: 0.72em; letter-spacing: 0.04em; text-transform: uppercase;
    color: #8a8f98; margin-bottom: 0.35rem;
}
#typeans { width: 100%; box-sizing: border-box; font-size: 0.95em; padding: 0.5rem 0.6rem; }
.sa-solution {
    margin-top: 1.4rem; padding: 0.85rem 1rem;
    border: 1px solid #e6e7eb; border-left: 4px solid #6366f1;
    border-radius: 10px; background: #eef0fb;
}
.sa-solution-h {
    font-size: 0.68em; font-weight: 700; letter-spacing: 0.07em;
    text-transform: uppercase; color: #6366f1; margin-bottom: 0.45rem;
}
.sa-solution-b { line-height: 1.6; }
/* Long display equations scroll horizontally instead of spilling past the card. */
mjx-container[display="true"] {
    margin: 0.6em 0; max-width: 100%; overflow-x: auto; overflow-y: hidden;
}
"""


def ensure_short_answer_notetype(col: Collection) -> Any:
    """Get (or create) the "SOA Short Answer" notetype: Front / Answer /
    Explanation, with a ``{{type:Answer}}`` typed-input template so numerical
    questions are answered by typing, not flipping. The answer view shows a
    labelled **Solution** block (the worked derivation, MathJax-rendered).
    Idempotent.

    The seeded study deck no longer uses this — ``build_deck`` files every card
    as a Basic flip card. It remains ONLY for the AI-generated *quarantine* deck
    (``anki.speedrun.ai.add_generated_cards``), whose exam-style items stay typed
    until a human approves them."""
    existing = col.models.by_name(SHORT_ANSWER_NOTETYPE)
    if existing is not None:
        return existing
    mm = col.models
    notetype = mm.new(SHORT_ANSWER_NOTETYPE)
    for field_name in ("Front", "Answer", "Explanation"):
        mm.add_field(notetype, mm.new_field(field_name))
    template = mm.new_template("Card 1")
    template["qfmt"] = (
        '<div class="sa-card">\n'
        '  <div class="sa-q">{{Front}}</div>\n'
        '  <div class="sa-prompt">Type your answer</div>\n'
        "  {{type:Answer}}\n"
        "</div>"
    )
    template["afmt"] = (
        '<div class="sa-card">\n'
        '  <div class="sa-q">{{Front}}</div>\n'
        "  {{type:Answer}}\n"
        "  {{#Explanation}}\n"
        '  <div class="sa-solution">\n'
        '    <div class="sa-solution-h">Solution</div>\n'
        '    <div class="sa-solution-b">{{Explanation}}</div>\n'
        "  </div>\n"
        "  {{/Explanation}}\n"
        "</div>"
    )
    mm.add_template(notetype, template)
    notetype["css"] = _SHORT_ANSWER_CSS
    mm.add(notetype)  # mutates `notetype` with its new id + ordinals
    return notetype


def basic_back(answer: str, solution: str) -> str:
    """Compose the Back of a computational card for the stock **Basic** notetype:
    the concise final answer, then the worked solution beneath it.

    Self-contained inline styling (no custom notetype or extra CSS needed), and
    MathJax ``\\( \\)`` / ``\\[ \\]`` is passed through untouched so Anki renders
    it. Used for fresh seeds and by the short-answer -> Basic migration, so both
    paths format the Back identically."""
    answer = (answer or "").strip()
    solution = (solution or "").strip()
    parts: list[str] = []
    if answer:
        parts.append(
            '<div style="font-weight:700;margin-bottom:0.5em">'
            f"Answer: {answer}</div>"
        )
    if solution:
        parts.append(f'<div style="text-align:left;line-height:1.5">{solution}</div>')
    return "\n".join(parts)


def build_deck(col: Collection, root: str = ROOT_DECK) -> int:
    """Create the tagged Exam P deck in ``col``. Returns the number of cards added.

    Every card is a stock **Basic** front/back flashcard the student self-grades
    (Again/Hard/Good/Easy). Computational ("numeric") cards show the concise
    answer plus the worked solution on the Back (``basic_back``); memorization
    cards use the plain definition/fact as the Back. No typed ``{{type:Answer}}``
    entry — we trust the learner to grade honestly.
    """
    topics = load_topics()
    basic = col.models.by_name("Basic")
    if basic is None:
        raise RuntimeError("Basic notetype not found in collection")

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
        note = col.new_note(basic)
        note["Front"] = card.front
        if card.kind == KIND_NUMERIC:
            note["Back"] = basic_back(card.answer, card.back)
        else:
            note["Back"] = card.back
        note.add_tag(unit_tag(card.unit_id))
        note.add_tag(subtopic_tag(card.unit_id, card.subtopic_id))
        note.add_tag(difficulty_tag(card.difficulty))
        # Every seeded card is a self-graded flip card now (memory track).
        note.add_tag("format::flashcard")
        col.add_note(note, deck_id)
        added += 1
    # Make the per-subtopic weights available to the engine's points-at-stake
    # live review order (ordering only; never affects any score).
    apply_subtopic_weights_config(col, topics)
    # Write the guided-learning DAG (subtopic/unit prerequisites) so the live
    # new-card gate can lock topics until their prerequisites are satisfied.
    apply_prereqs_config(col, topics)
    # Turn the three-tier mastery scheduler ON for this deck, so the tier-aware
    # new-card order is actually LIVE in the review queue (not just an available
    # default-off flag). It is a read-only reorder in build_queues, so FSRS
    # intervals and undo/integrity are untouched. The study-feature ablation
    # selects its builds through its own harness, so enabling it here does not
    # bias that experiment.
    col.set_config("speedrunMasteryScheduler", True)
    # Performance-first app: the guided sequence is ADVISORY (recommended next
    # topic + arrows on the map), never a hard gate. Turn the gate OFF so no
    # subtopic's new cards are ever withheld — the learner can practice anything,
    # any time. (The DAG is still used to recommend an order; it just no longer
    # locks.) Kept as config, not a Rust default change, so upstream Anki + the
    # ablation harness are untouched.
    col.set_config("speedrunGuidedMode", False)
    # Turn FSRS ON for this app. The Memory signal IS FSRS retrievability, and the
    # mastery gate needs retrievability >= 0.90, so without FSRS the whole memory
    # side reads 0. FSRS is Anki's own algorithm (not a reimplementation); we just
    # enable it so the three signals are all live.
    col.set_config("fsrs", True)
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


def convert_seeded_short_answer_to_basic(col: Collection) -> int:
    """Convert already-seeded typed "SOA Short Answer" curriculum cards into stock
    **Basic** flip cards (the new format), in place. Returns the number converted.

    A collection seeded before this change still holds the old typed cards (the
    seed runs once, guarded by ``SEEDED_KEY``, so it never rebuilds). This is the
    idempotent, reproducible fix — run it once via
    ``tools/speedrun/convert_short_answer_to_basic.py`` with Anki CLOSED.

    Safety / scope:
      * SCOPED to seeded curriculum cards only — matched by the ``difficulty::``
        tag every seeded card carries. The AI-generated *quarantine* cards share
        the same notetype but never carry a ``difficulty::`` tag, so they are left
        exactly as-is (the performance/AI track is untouched).
      * Uses Anki's own ``models.change`` note-type conversion, mapping the single
        card template 1:1 (``{0: 0}``), so each card KEEPS its FSRS scheduling and
        review history and undo still works — the collection is never corrupted.
      * Idempotent: once converted there are no matching notes left, so a second
        run is a no-op (and does not touch the schema).

    The Back is rebuilt with :func:`basic_back` (answer + worked solution), so a
    converted card renders identically to a freshly seeded one; the format tag is
    flipped ``short_answer`` -> ``flashcard``.
    """
    short_answer = col.models.by_name(SHORT_ANSWER_NOTETYPE)
    if short_answer is None:
        return 0
    basic = col.models.by_name("Basic")
    if basic is None:
        raise RuntimeError("Basic notetype not found in collection")

    # Seeded curriculum cards only (difficulty::*). Never the AI quarantine cards.
    nids = list(
        col.find_notes(f'note:"{SHORT_ANSWER_NOTETYPE}" tag:difficulty::*')
    )
    if not nids:
        return 0

    # 1) Fold Answer + Explanation into the field we map to Back, and retag the
    #    card as a self-graded flip card. (Per-note content edit; not a schema op.)
    for nid in nids:
        note = col.get_note(nid)
        note["Explanation"] = basic_back(note["Answer"], note["Explanation"])
        note.tags = [
            "format::flashcard" if t == "format::short_answer" else t
            for t in note.tags
        ]
        if "format::flashcard" not in note.tags:
            note.add_tag("format::flashcard")
        col.update_note(note)

    # 2) Convert the notetype in one bulk op: Front->Front, Explanation->Back,
    #    Answer discarded; the lone card template maps 1:1 so scheduling survives.
    col.models.change(
        short_answer,
        nids,
        basic,
        {0: 0, 1: None, 2: 1},
        {0: 0},
    )
    return len(nids)
