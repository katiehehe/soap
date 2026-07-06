// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

// Curated Exam P formula reference, grouped by the official syllabus taxonomy
// (the same TAXONOMY the study map and scheduler use). This is a REFERENCE
// surface only, so nothing here logs a review, schedules a card, or touches any
// score. Every formula is a standard, textbook result and cites a NAMED source
// (Exam P is not one of the rubric's example exams, so provenance matters):
//
//   * SOA Exam P syllabus (the published outline of examinable topics), and
//   * Ross, A First Course in Probability, and
//   * Hassett & Stewart, Probability for Risk Management (the actuarial text
//     covering deductibles/limits and the standard named distributions).
//
// Formulas are NOT invented here; they restate results already relied on by the
// seed content (pylib/anki/speedrun/seed.py) and the named source passages in
// pylib/anki/speedrun/gen_sources.json. LaTeX is written with String.raw and
// full \[ ... \] delimiters so the MathJax action typesets it verbatim.

import { subtopicTag } from "../study-map/lib";

/** Named, citable sources. Kept as constants so every formula's provenance is
 * consistent and greppable (never a bare, unattributed claim). */
export const SOURCES = {
    soa: "SOA Exam P syllabus",
    ross: "Ross, A First Course in Probability",
    hassett: "Hassett & Stewart, Probability for Risk Management",
} as const;

export type SourceName = (typeof SOURCES)[keyof typeof SOURCES];

export interface Formula {
    /** Short label for the identity (also used as the {#each} key). */
    name: string;
    /** MathJax LaTeX, including its own \[ ... \] / \( ... \) delimiters. */
    latex: string;
    /** Optional one-line, plain-language gloss (also fed to the keyword search). */
    note?: string;
    /** The named source this result is drawn from. */
    source: SourceName;
}

// Formulas keyed by the subtopic tag `subtopic::<unit>::<id>`, so the page can
// walk TAXONOMY (3 units → 19 subtopics) and look each set up directly.
export const FORMULAS: Record<string, Formula[]> = {
    // ---- General Probability ------------------------------------------------
    [subtopicTag("general", "sets_axioms")]: [
        {
            name: "Probability axioms",
            latex: String.raw`\[ 0 \le P(A) \le 1, \quad P(S)=1 \]`,
            note: "A probability lies in [0,1]; the whole sample space has probability 1.",
            source: SOURCES.ross,
        },
        {
            name: "Countable additivity",
            latex: String.raw`\[ P\!\left(\bigcup_i A_i\right) = \sum_i P(A_i) \quad (A_i \text{ disjoint}) \]`,
            note: "For disjoint events the probability of the union is the sum.",
            source: SOURCES.ross,
        },
        {
            name: "Complement rule",
            latex: String.raw`\[ P(A^{c}) = 1 - P(A) \]`,
            source: SOURCES.ross,
        },
        {
            name: "Monotonicity",
            latex: String.raw`\[ A \subseteq B \implies P(A) \le P(B) \]`,
            source: SOURCES.ross,
        },
        {
            name: "De Morgan's laws",
            latex: String.raw`\[ (A \cup B)^{c} = A^{c} \cap B^{c}, \quad (A \cap B)^{c} = A^{c} \cup B^{c} \]`,
            source: SOURCES.soa,
        },
    ],
    [subtopicTag("general", "combinatorics")]: [
        {
            name: "Permutations",
            latex: String.raw`\[ {}_{n}P_{k} = \frac{n!}{(n-k)!} \]`,
            note: "Ordered arrangements of k items from n.",
            source: SOURCES.ross,
        },
        {
            name: "Combinations",
            latex: String.raw`\[ \binom{n}{k} = \frac{n!}{k!\,(n-k)!} \]`,
            note: "Unordered selections of k items from n.",
            source: SOURCES.ross,
        },
        {
            name: "Multiplication principle",
            latex: String.raw`\[ N = n_{1} \times n_{2} \times \cdots \times n_{k} \]`,
            source: SOURCES.ross,
        },
        {
            name: "Binomial theorem",
            latex: String.raw`\[ (x+y)^{n} = \sum_{k=0}^{n} \binom{n}{k} x^{k} y^{\,n-k} \]`,
            source: SOURCES.ross,
        },
    ],
    [subtopicTag("general", "add_mult_rules")]: [
        {
            name: "Addition rule",
            latex: String.raw`\[ P(A \cup B) = P(A) + P(B) - P(A \cap B) \]`,
            source: SOURCES.ross,
        },
        {
            name: "Mutually exclusive events",
            latex: String.raw`\[ P(A \cup B) = P(A) + P(B) \quad (A \cap B = \varnothing) \]`,
            source: SOURCES.ross,
        },
        {
            name: "Multiplication rule",
            latex: String.raw`\[ P(A \cap B) = P(A)\,P(B \mid A) \]`,
            source: SOURCES.ross,
        },
        {
            name: "Inclusion-exclusion (three events)",
            latex: String.raw`\[ P(A \cup B \cup C) = P(A)+P(B)+P(C) - P(A \cap B) - P(A \cap C) - P(B \cap C) + P(A \cap B \cap C) \]`,
            source: SOURCES.ross,
        },
    ],
    [subtopicTag("general", "independence")]: [
        {
            name: "Independent events",
            latex: String.raw`\[ P(A \cap B) = P(A)\,P(B) \]`,
            note: "Equivalently, conditioning on one does not change the other.",
            source: SOURCES.ross,
        },
        {
            name: "Independence and conditioning",
            latex: String.raw`\[ P(A \mid B) = P(A) \]`,
            source: SOURCES.ross,
        },
        {
            name: "Series system reliability",
            latex: String.raw`\[ P(\text{works}) = \prod_{i=1}^{n} p_{i} \]`,
            note: "Independent components in series all must work.",
            source: SOURCES.hassett,
        },
        {
            name: "Parallel system reliability",
            latex: String.raw`\[ P(\text{works}) = 1 - \prod_{i=1}^{n} (1 - p_{i}) \]`,
            source: SOURCES.hassett,
        },
    ],
    [subtopicTag("general", "conditional")]: [
        {
            name: "Conditional probability",
            latex: String.raw`\[ P(A \mid B) = \frac{P(A \cap B)}{P(B)}, \quad P(B) > 0 \]`,
            source: SOURCES.ross,
        },
        {
            name: "Law of total probability",
            latex: String.raw`\[ P(B) = \sum_{i} P(B \mid A_{i})\,P(A_{i}) \]`,
            note: "Over a partition A₁,…,Aₙ of the sample space.",
            source: SOURCES.ross,
        },
        {
            name: "Chain (multiplication) rule",
            latex: String.raw`\[ P(A \cap B) = P(B)\,P(A \mid B) \]`,
            source: SOURCES.ross,
        },
    ],
    [subtopicTag("general", "bayes")]: [
        {
            name: "Bayes' theorem",
            latex: String.raw`\[ P(A \mid B) = \frac{P(B \mid A)\,P(A)}{P(B)} \]`,
            note: "Updates a prior P(A) into a posterior after observing B.",
            source: SOURCES.ross,
        },
        {
            name: "Bayes with total probability",
            latex: String.raw`\[ P(A_{j} \mid B) = \frac{P(B \mid A_{j})\,P(A_{j})}{\sum_{i} P(B \mid A_{i})\,P(A_{i})} \]`,
            source: SOURCES.ross,
        },
    ],
    // ---- Univariate Random Variables ---------------------------------------
    [subtopicTag("univariate", "rv_basics")]: [
        {
            name: "Density function",
            latex: String.raw`\[ f(x) \ge 0, \quad \int_{-\infty}^{\infty} f(x)\,dx = 1 \]`,
            source: SOURCES.ross,
        },
        {
            name: "Cumulative distribution function",
            latex: String.raw`\[ F(x) = P(X \le x) = \int_{-\infty}^{x} f(t)\,dt \]`,
            source: SOURCES.ross,
        },
        {
            name: "Density from the CDF",
            latex: String.raw`\[ f(x) = F'(x) \]`,
            source: SOURCES.ross,
        },
        {
            name: "Interval probability",
            latex: String.raw`\[ P(a < X \le b) = F(b) - F(a) \]`,
            source: SOURCES.ross,
        },
        {
            name: "Probability mass function",
            latex: String.raw`\[ p(x) \ge 0, \quad \sum_{x} p(x) = 1 \]`,
            source: SOURCES.ross,
        },
    ],
    [subtopicTag("univariate", "expectation")]: [
        {
            name: "Expected value",
            latex: String.raw`\[ E[X] = \int_{-\infty}^{\infty} x\,f(x)\,dx = \sum_{x} x\,p(x) \]`,
            source: SOURCES.ross,
        },
        {
            name: "Law of the unconscious statistician",
            latex: String.raw`\[ E[g(X)] = \int_{-\infty}^{\infty} g(x)\,f(x)\,dx \]`,
            source: SOURCES.ross,
        },
        {
            name: "Linearity of expectation",
            latex: String.raw`\[ E[aX + b] = a\,E[X] + b \]`,
            source: SOURCES.ross,
        },
        {
            name: "Moment generating function",
            latex: String.raw`\[ M_{X}(t) = E\!\left[e^{tX}\right], \quad E[X^{n}] = M_{X}^{(n)}(0) \]`,
            note: "The n-th derivative at 0 gives the n-th raw moment.",
            source: SOURCES.hassett,
        },
    ],
    [subtopicTag("univariate", "variance")]: [
        {
            name: "Variance",
            latex: String.raw`\[ \operatorname{Var}(X) = E[X^{2}] - \big(E[X]\big)^{2} \]`,
            source: SOURCES.ross,
        },
        {
            name: "Variance under scaling",
            latex: String.raw`\[ \operatorname{Var}(aX + b) = a^{2}\,\operatorname{Var}(X) \]`,
            source: SOURCES.ross,
        },
        {
            name: "Standard deviation",
            latex: String.raw`\[ \sigma_{X} = \sqrt{\operatorname{Var}(X)} \]`,
            source: SOURCES.ross,
        },
        {
            name: "Coefficient of variation",
            latex: String.raw`\[ \mathrm{CV} = \frac{\sigma_{X}}{E[X]} \]`,
            source: SOURCES.hassett,
        },
    ],
    [subtopicTag("univariate", "discrete_dists")]: [
        {
            name: "Binomial(n, p)",
            latex: String.raw`\[ P(X=k) = \binom{n}{k} p^{k} (1-p)^{n-k}, \quad E[X]=np, \ \operatorname{Var}(X)=np(1-p) \]`,
            source: SOURCES.hassett,
        },
        {
            name: "Poisson(λ)",
            latex: String.raw`\[ P(X=k) = \frac{e^{-\lambda}\lambda^{k}}{k!}, \quad E[X]=\operatorname{Var}(X)=\lambda \]`,
            source: SOURCES.hassett,
        },
        {
            name: "Geometric(p)",
            latex: String.raw`\[ P(X=k) = (1-p)^{k-1} p, \quad E[X]=\frac{1}{p}, \ \operatorname{Var}(X)=\frac{1-p}{p^{2}} \]`,
            source: SOURCES.hassett,
        },
        {
            name: "Negative binomial(r, p)",
            latex: String.raw`\[ E[X] = \frac{r}{p}, \quad \operatorname{Var}(X) = \frac{r(1-p)}{p^{2}} \]`,
            source: SOURCES.hassett,
        },
        {
            name: "Hypergeometric mean",
            latex: String.raw`\[ E[X] = n\,\frac{K}{N} \]`,
            note: "Sampling n without replacement from N with K successes.",
            source: SOURCES.hassett,
        },
    ],
    [subtopicTag("univariate", "continuous_dists")]: [
        {
            name: "Uniform(a, b)",
            latex: String.raw`\[ f(x) = \frac{1}{b-a}, \quad E[X] = \frac{a+b}{2}, \ \operatorname{Var}(X) = \frac{(b-a)^{2}}{12} \]`,
            source: SOURCES.hassett,
        },
        {
            name: "Exponential(λ)",
            latex: String.raw`\[ f(x) = \lambda e^{-\lambda x}, \quad E[X] = \frac{1}{\lambda}, \ \operatorname{Var}(X) = \frac{1}{\lambda^{2}} \]`,
            source: SOURCES.hassett,
        },
        {
            name: "Memoryless property",
            latex: String.raw`\[ P(X > s + t \mid X > s) = P(X > t) \]`,
            note: "Characterises the exponential distribution.",
            source: SOURCES.hassett,
        },
        {
            name: "Normal(μ, σ²)",
            latex: String.raw`\[ f(x) = \frac{1}{\sigma\sqrt{2\pi}}\, e^{-\frac{(x-\mu)^{2}}{2\sigma^{2}}} \]`,
            source: SOURCES.ross,
        },
        {
            name: "Gamma(α, λ)",
            latex: String.raw`\[ E[X] = \frac{\alpha}{\lambda}, \quad \operatorname{Var}(X) = \frac{\alpha}{\lambda^{2}} \]`,
            source: SOURCES.hassett,
        },
    ],
    [subtopicTag("univariate", "insurance_apps")]: [
        {
            name: "Payment with an ordinary deductible d",
            latex: String.raw`\[ Y = (X - d)_{+} = \max(X - d,\, 0) \]`,
            source: SOURCES.hassett,
        },
        {
            name: "Expected payment (deductible)",
            latex: String.raw`\[ E\big[(X-d)_{+}\big] = \int_{d}^{\infty} (x - d)\,f(x)\,dx \]`,
            source: SOURCES.hassett,
        },
        {
            name: "Policy limit u",
            latex: String.raw`\[ Y = \min(X,\, u) \]`,
            source: SOURCES.hassett,
        },
        {
            name: "Mean via the survival function",
            latex: String.raw`\[ E[X] = \int_{0}^{\infty} S(x)\,dx, \quad S(x) = 1 - F(x) \]`,
            note: "For a non-negative loss X.",
            source: SOURCES.hassett,
        },
    ],
    // ---- Multivariate Random Variables -------------------------------------
    [subtopicTag("multivariate", "joint_distributions")]: [
        {
            name: "Joint density",
            latex: String.raw`\[ f(x,y) \ge 0, \quad \iint_{\mathbb{R}^{2}} f(x,y)\,dx\,dy = 1 \]`,
            source: SOURCES.ross,
        },
        {
            name: "Probability over a region",
            latex: String.raw`\[ P\big((X,Y) \in A\big) = \iint_{A} f(x,y)\,dx\,dy \]`,
            source: SOURCES.ross,
        },
        {
            name: "Joint mass function",
            latex: String.raw`\[ \sum_{x} \sum_{y} p(x,y) = 1 \]`,
            source: SOURCES.ross,
        },
        {
            name: "Joint CDF",
            latex: String.raw`\[ F(x,y) = P(X \le x,\, Y \le y) \]`,
            source: SOURCES.ross,
        },
    ],
    [subtopicTag("multivariate", "marginal_conditional")]: [
        {
            name: "Marginal density",
            latex: String.raw`\[ f_{X}(x) = \int_{-\infty}^{\infty} f(x,y)\,dy \]`,
            source: SOURCES.ross,
        },
        {
            name: "Conditional density",
            latex: String.raw`\[ f_{Y \mid X}(y \mid x) = \frac{f(x,y)}{f_{X}(x)} \]`,
            note: "Defined wherever the marginal fₓ(x) is positive.",
            source: SOURCES.ross,
        },
        {
            name: "Independence of X and Y",
            latex: String.raw`\[ f(x,y) = f_{X}(x)\,f_{Y}(y) \]`,
            source: SOURCES.ross,
        },
    ],
    [subtopicTag("multivariate", "joint_moments")]: [
        {
            name: "Expectation of g(X, Y)",
            latex: String.raw`\[ E[g(X,Y)] = \iint g(x,y)\,f(x,y)\,dx\,dy \]`,
            source: SOURCES.ross,
        },
        {
            name: "Expectation of the product",
            latex: String.raw`\[ E[XY] = \iint xy\,f(x,y)\,dx\,dy \]`,
            source: SOURCES.ross,
        },
        {
            name: "Linearity of expectation",
            latex: String.raw`\[ E[aX + bY] = a\,E[X] + b\,E[Y] \]`,
            source: SOURCES.ross,
        },
        {
            name: "Independence factorisation",
            latex: String.raw`\[ X \perp Y \implies E[XY] = E[X]\,E[Y] \]`,
            source: SOURCES.ross,
        },
    ],
    [subtopicTag("multivariate", "covariance_correlation")]: [
        {
            name: "Covariance",
            latex: String.raw`\[ \operatorname{Cov}(X,Y) = E[XY] - E[X]\,E[Y] \]`,
            source: SOURCES.ross,
        },
        {
            name: "Correlation coefficient",
            latex: String.raw`\[ \rho_{XY} = \frac{\operatorname{Cov}(X,Y)}{\sigma_{X}\,\sigma_{Y}}, \quad -1 \le \rho_{XY} \le 1 \]`,
            source: SOURCES.ross,
        },
        {
            name: "Bilinearity of covariance",
            latex: String.raw`\[ \operatorname{Cov}(aX + b,\, cY + d) = ac\,\operatorname{Cov}(X,Y) \]`,
            source: SOURCES.ross,
        },
        {
            name: "Variance of a sum",
            latex: String.raw`\[ \operatorname{Var}(X + Y) = \operatorname{Var}(X) + \operatorname{Var}(Y) + 2\operatorname{Cov}(X,Y) \]`,
            source: SOURCES.ross,
        },
    ],
    [subtopicTag("multivariate", "order_statistics")]: [
        {
            name: "Maximum: CDF",
            latex: String.raw`\[ F_{(n)}(x) = [F(x)]^{n} \]`,
            note: "For n i.i.d. variables, the max is ≤ x iff all are.",
            source: SOURCES.ross,
        },
        {
            name: "Minimum: CDF",
            latex: String.raw`\[ F_{(1)}(x) = 1 - [1 - F(x)]^{n} \]`,
            source: SOURCES.ross,
        },
        {
            name: "Maximum: density",
            latex: String.raw`\[ f_{(n)}(x) = n\,[F(x)]^{n-1} f(x) \]`,
            source: SOURCES.ross,
        },
        {
            name: "Minimum: density",
            latex: String.raw`\[ f_{(1)}(x) = n\,[1 - F(x)]^{n-1} f(x) \]`,
            source: SOURCES.ross,
        },
    ],
    [subtopicTag("multivariate", "linear_combinations")]: [
        {
            name: "Mean of a linear combination",
            latex: String.raw`\[ E\!\left[\sum_{i} a_{i} X_{i}\right] = \sum_{i} a_{i}\,E[X_{i}] \]`,
            source: SOURCES.ross,
        },
        {
            name: "Variance of aX + bY",
            latex: String.raw`\[ \operatorname{Var}(aX + bY) = a^{2}\operatorname{Var}(X) + b^{2}\operatorname{Var}(Y) + 2ab\,\operatorname{Cov}(X,Y) \]`,
            source: SOURCES.ross,
        },
        {
            name: "Independent sum: variances add",
            latex: String.raw`\[ X \perp Y \implies \operatorname{Var}(X + Y) = \operatorname{Var}(X) + \operatorname{Var}(Y) \]`,
            source: SOURCES.ross,
        },
        {
            name: "MGF of an independent sum",
            latex: String.raw`\[ M_{X+Y}(t) = M_{X}(t)\,M_{Y}(t) \]`,
            source: SOURCES.ross,
        },
    ],
    [subtopicTag("multivariate", "clt")]: [
        {
            name: "Sample mean",
            latex: String.raw`\[ \bar{X}_{n} \approx \mathcal{N}\!\left(\mu,\ \frac{\sigma^{2}}{n}\right) \]`,
            note: "For large n, with i.i.d. terms of mean μ and variance σ².",
            source: SOURCES.ross,
        },
        {
            name: "Sum of i.i.d. variables",
            latex: String.raw`\[ \sum_{i=1}^{n} X_{i} \approx \mathcal{N}\!\left(n\mu,\ n\sigma^{2}\right) \]`,
            source: SOURCES.ross,
        },
        {
            name: "Standardised sample mean",
            latex: String.raw`\[ Z = \frac{\bar{X}_{n} - \mu}{\sigma / \sqrt{n}} \ \longrightarrow \ \mathcal{N}(0,1) \]`,
            source: SOURCES.ross,
        },
    ],
};

/** Formulas for one subtopic tag (empty list if none are curated yet). */
export function formulasForTag(tag: string): Formula[] {
    return FORMULAS[tag] ?? [];
}
