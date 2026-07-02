<!--
Copyright: Ankitects Pty Ltd and contributors
License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
-->
<script lang="ts">
    import { onMount } from "svelte";

    import { computeReadiness } from "@generated/backend";
    import type { ReadinessResult } from "@generated/anki/speedrun_pb";

    // Mirrors pylib/anki/speedrun/exam_p_topics.json (official 2026-05 outline).
    // A future RPC will serve the syllabus so there is a single source.
    const EXPECTED_SUBTOPICS = [
        "subtopic::general::sets_axioms",
        "subtopic::general::combinatorics",
        "subtopic::general::independence",
        "subtopic::general::add_mult_rules",
        "subtopic::general::conditional",
        "subtopic::general::bayes",
        "subtopic::univariate::rv_basics",
        "subtopic::univariate::expectation",
        "subtopic::univariate::variance",
        "subtopic::univariate::discrete_dists",
        "subtopic::univariate::continuous_dists",
        "subtopic::univariate::insurance_apps",
        "subtopic::multivariate::joint_distributions",
        "subtopic::multivariate::marginal_conditional",
        "subtopic::multivariate::joint_moments",
        "subtopic::multivariate::covariance_correlation",
        "subtopic::multivariate::order_statistics",
        "subtopic::multivariate::linear_combinations",
        "subtopic::multivariate::clt",
    ];

    // Official SOA P section weights (range midpoints) so coverage is weighted:
    // skipping a high-weight section can't read as "covered".
    const UNIT_WEIGHTS = [
        { unitId: "general", weight: 26.5 },
        { unitId: "univariate", weight: 47 },
        { unitId: "multivariate", weight: 26.5 },
    ];

    let result: ReadinessResult | null = null;
    let loadError = "";

    onMount(async () => {
        try {
            result = await computeReadiness({
                expectedSubtopics: EXPECTED_SUBTOPICS,
                units: UNIT_WEIGHTS,
            });
        } catch (err) {
            loadError = String(err);
        }
    });

    $: noScore = result?.value.case === "noScore" ? result.value.value : null;
    $: score = result?.value.case === "score" ? result.value.value : null;
    $: coveragePct = noScore?.coveragePct ?? score?.coveragePct ?? 0;
    $: gradedReviews = noScore?.gradedReviews ?? 0;
    $: nextAction = noScore?.nextBestAction ?? score?.nextBestAction ?? "—";
    // Distinguish the abstain reasons honestly: below the review/coverage gate
    // vs. gate met but awaiting graded practice-test evidence.
    $: readinessNeedsPractice =
        !!noScore && noScore.reason.toLowerCase().includes("practice");
    $: readinessAbstainValue = readinessNeedsPractice
        ? "Take a practice test"
        : "Not enough data yet";
    $: readinessAbstainDetail = readinessNeedsPractice
        ? "review gate met; needs graded practice tests"
        : "held below threshold";

    function pct(x: number): string {
        return `${Math.round(x * 100)}%`;
    }

    // The three signals, shown side by side and never blended into one number.
    // Only readiness is computed today; memory/performance stay explicitly
    // "not yet calibrated" rather than showing a fabricated value.
    type SignalState = "pending" | "giveup" | "score";
    interface Signal {
        name: string;
        question: string;
        state: SignalState;
        value: string;
        detail: string;
        source: string;
    }

    $: signals = [
        {
            name: "Memory",
            question: "Can you recall the fact right now?",
            state: "pending",
            value: "Not yet scored",
            detail:
                gradedReviews > 0
                    ? `${gradedReviews} graded reviews on file`
                    : "no reviews yet",
            source: "FSRS review history",
        },
        {
            name: "Performance",
            question: "Can you solve a new, exam-style question?",
            state: "pending",
            value: "Not yet measured",
            detail: "needs exam-style items",
            source: "Performance model",
        },
        {
            name: "Readiness",
            question: "Would you pass today, and how sure are we?",
            state: score ? "score" : "giveup",
            value: score
                ? `${score.point.toFixed(1)} (${score.low.toFixed(1)}–${score.high.toFixed(1)})`
                : readinessAbstainValue,
            detail: score
                ? `P(pass) ${pct(score.passProbability)} · confidence ${pct(score.confidence)}`
                : readinessAbstainDetail,
            source: "P(pass) model",
        },
    ] as Signal[];
</script>

<div class="readiness">
    <header>
        <h1>Exam readiness</h1>
        <p class="exam">SOA Exam P · Probability</p>
        <p class="subtitle">Three separate signals, never blended into one number.</p>
    </header>

    {#if loadError}
        <div class="panel error">
            <h2>Couldn't compute readiness</h2>
            <p>{loadError}</p>
        </div>
    {:else if result === null}
        <div class="panel muted">Computing readiness…</div>
    {:else}
        <section class="signals" aria-label="The three signals">
            {#each signals as s}
                <article class="signal {s.state}">
                    <div class="signal-head">
                        <span class="dot" aria-hidden="true"></span>
                        <h2>{s.name}</h2>
                    </div>
                    <p class="question">{s.question}</p>
                    <p class="value">{s.value}</p>
                    <p class="detail">{s.detail}</p>
                    <p class="source">{s.source}</p>
                </article>
            {/each}
        </section>

        {#if noScore}
            <section class="panel detail-panel">
                <div class="panel-head">
                    <h2>Readiness</h2>
                    <span class="badge">Not enough data yet</span>
                </div>
                <p class="reason">{noScore.reason}</p>
                <div class="metrics">
                    <div class="metric">
                        <span class="label">Graded reviews</span>
                        <span class="metric-value">{noScore.gradedReviews} / 200</span>
                        <div class="bar">
                            <span
                                class="bar-fill"
                                style="width: {Math.min(
                                    100,
                                    (noScore.gradedReviews / 200) * 100,
                                )}%"
                            ></span>
                        </div>
                        <span class="hint">{noScore.reviewsNeeded} more needed</span>
                    </div>
                    <div class="metric">
                        <span class="label">Syllabus practiced</span>
                        <span class="metric-value">{pct(coveragePct)}</span>
                        <div class="bar">
                            <span
                                class="bar-fill"
                                style="width: {Math.min(100, coveragePct * 100)}%"
                            ></span>
                        </div>
                        <span class="hint">
                            subtopics studied ≥ 1× · need ≥ 50% (weighted by section)
                        </span>
                    </div>
                </div>
                <div class="next-action">
                    <span class="label">Single best next action</span>
                    <p>{noScore.nextBestAction}</p>
                </div>
            </section>
        {:else if score}
            <section class="panel detail-panel score-panel">
                <div class="panel-head">
                    <h2>Readiness</h2>
                    <span class="badge ok">Score available</span>
                </div>
                <div class="point">
                    {score.point.toFixed(1)}
                    <span class="range">
                        ({score.low.toFixed(1)}–{score.high.toFixed(1)})
                    </span>
                </div>
                <p class="hint">
                    Coverage {pct(score.coveragePct)} · confidence {pct(
                        score.confidence,
                    )}
                </p>
                <p class="pass-prob">
                    P(pass today): <b>{pct(score.passProbability)}</b>
                    <span class="hint">(scaled ≥ 6)</span>
                </p>
                <div class="next-action">
                    <span class="label">Single best next action</span>
                    <p>{score.nextBestAction}</p>
                </div>
            </section>
        {/if}

        <section class="panel bundle-panel">
            <h2>What every readiness report must show</h2>
            <p class="note">
                The give-up rule lives in the Rust engine: with fewer than 200 graded
                reviews <b>or</b>
                under 50% weighted
                <b>practiced</b>
                coverage (the share of subtopics you've actually studied, not just have cards
                for), no score is shown. A readiness number also needs ≥ 30 graded practice-test
                questions; until then these fields stay "—". We never fabricate a number.
            </p>
            <dl class="bundle">
                <div>
                    <dt>Point estimate</dt>
                    <dd>{score ? score.point.toFixed(1) : "—"}</dd>
                </div>
                <div>
                    <dt>Likely range</dt>
                    <dd>
                        {score
                            ? `${score.low.toFixed(1)}–${score.high.toFixed(1)}`
                            : "—"}
                    </dd>
                </div>
                <div>
                    <dt>Syllabus practiced</dt>
                    <dd>{pct(coveragePct)}</dd>
                </div>
                <div>
                    <dt>How sure (confidence)</dt>
                    <dd>{score ? pct(score.confidence) : "—"}</dd>
                </div>
                <div>
                    <dt>P(pass) today</dt>
                    <dd>{score ? pct(score.passProbability) : "—"}</dd>
                </div>
                <div>
                    <dt>How accurate past guesses were</dt>
                    <dd>
                        {score && score.pastAccuracy > 0
                            ? pct(score.pastAccuracy)
                            : "—"}
                    </dd>
                </div>
                <div>
                    <dt>Graded reviews</dt>
                    <dd>{gradedReviews}</dd>
                </div>
                <div>
                    <dt>Last updated</dt>
                    <dd>
                        {score
                            ? new Date(Number(score.updatedAt) * 1000).toLocaleString()
                            : "—"}
                    </dd>
                </div>
                <div>
                    <dt>Main reasons</dt>
                    <dd>
                        {score && score.reasons.length ? score.reasons.join("; ") : "—"}
                    </dd>
                </div>
                <div>
                    <dt>Single best next action</dt>
                    <dd>{nextAction}</dd>
                </div>
            </dl>
        </section>
    {/if}
</div>

<style>
    .readiness {
        max-width: 780px;
        margin: 0 auto;
        padding: 1.5rem 1.25rem 3rem;
        color: var(--fg, #1c1c1e);
        font-size: 15px;
        line-height: 1.45;
    }

    /* Header */
    header {
        margin-bottom: 1.5rem;
    }
    header h1 {
        margin: 0;
        font-size: 1.5rem;
        font-weight: 700;
    }
    header .exam {
        margin: 0.15rem 0 0;
        font-size: 0.85rem;
        font-weight: 600;
        letter-spacing: 0.02em;
        text-transform: uppercase;
        color: var(--fg-subtle, #6b7280);
    }
    header .subtitle {
        margin: 0.5rem 0 0;
        color: var(--fg-subtle, #4b5563);
    }

    /* Generic panel */
    .panel {
        border: 1px solid var(--border, #e2e2e5);
        border-radius: 10px;
        padding: 1.1rem 1.25rem;
        margin-bottom: 1rem;
        background: var(--canvas-elevated, #fbfbfc);
    }
    .panel.muted {
        color: var(--fg-subtle, #6b7280);
    }
    .panel.error {
        border-color: #d9534f;
    }
    .panel-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.75rem;
        margin-bottom: 0.5rem;
    }
    .panel-head h2 {
        margin: 0;
        font-size: 1.05rem;
    }

    /* Three-signal row */
    .signals {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
        gap: 0.85rem;
        margin-bottom: 1.25rem;
    }
    .signal {
        border: 1px solid var(--border, #e2e2e5);
        border-top: 3px solid var(--signal-color, #9ca3af);
        border-radius: 10px;
        padding: 0.9rem 1rem 1rem;
        background: var(--canvas-elevated, #fbfbfc);
    }
    .signal.pending {
        --signal-color: #9ca3af;
    }
    .signal.giveup {
        --signal-color: #d69e2e;
    }
    .signal.score {
        --signal-color: #38a169;
    }
    .signal-head {
        display: flex;
        align-items: center;
        gap: 0.4rem;
    }
    .signal-head h2 {
        margin: 0;
        font-size: 1rem;
        font-weight: 600;
    }
    .dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: var(--signal-color, #9ca3af);
        flex: 0 0 auto;
    }
    .signal .question {
        margin: 0.35rem 0 0.75rem;
        font-size: 0.82rem;
        color: var(--fg-subtle, #6b7280);
        min-height: 2.2em;
    }
    .signal .value {
        margin: 0;
        font-size: 1.1rem;
        font-weight: 700;
    }
    .signal .detail {
        margin: 0.1rem 0 0;
        font-size: 0.8rem;
        color: var(--fg-subtle, #6b7280);
    }
    .signal .source {
        margin: 0.6rem 0 0;
        font-size: 0.72rem;
        letter-spacing: 0.02em;
        text-transform: uppercase;
        color: var(--fg-subtle, #9ca3af);
    }

    /* Readiness detail */
    .badge {
        display: inline-block;
        background: var(--signal-amber-bg, rgba(214, 158, 46, 0.16));
        color: #915c05;
        font-weight: 600;
        border-radius: 999px;
        padding: 0.2rem 0.7rem;
        font-size: 0.78rem;
        white-space: nowrap;
    }
    .badge.ok {
        background: rgba(56, 161, 105, 0.16);
        color: #216c46;
    }
    .reason {
        margin: 0 0 1rem;
        color: var(--fg, #1c1c1e);
    }
    .metrics {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 1.25rem;
        margin-bottom: 1rem;
    }
    .metric {
        display: flex;
        flex-direction: column;
        gap: 0.25rem;
    }
    .label {
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.03em;
        color: var(--fg-subtle, #6b7280);
    }
    .metric-value {
        font-size: 1.5rem;
        font-weight: 700;
        line-height: 1.1;
    }
    .bar {
        height: 6px;
        border-radius: 999px;
        background: var(--canvas-inset, #ececef);
        overflow: hidden;
    }
    .bar-fill {
        display: block;
        height: 100%;
        background: var(--fg-subtle, #6b7280);
        border-radius: 999px;
    }
    .metric .hint,
    .score-panel .hint {
        font-size: 0.8rem;
        color: var(--fg-subtle, #6b7280);
    }
    .next-action {
        border-top: 1px solid var(--border, #e2e2e5);
        padding-top: 0.75rem;
    }
    .next-action p {
        margin: 0.25rem 0 0;
        font-weight: 600;
    }
    .score-panel .point {
        font-size: 2.4rem;
        font-weight: 800;
        line-height: 1;
    }
    .score-panel .range {
        font-size: 1rem;
        font-weight: 400;
        color: var(--fg-subtle, #6b7280);
    }
    .pass-prob {
        margin: 0.4rem 0 0;
        font-size: 1rem;
    }
    .pass-prob b {
        font-size: 1.15rem;
    }

    /* Honesty bundle */
    .bundle-panel h2 {
        margin: 0 0 0.4rem;
        font-size: 1.05rem;
    }
    .note {
        margin: 0 0 0.75rem;
        color: var(--fg-subtle, #4b5563);
        font-size: 0.88rem;
    }
    .bundle {
        margin: 0;
    }
    .bundle > div {
        display: flex;
        justify-content: space-between;
        gap: 1rem;
        padding: 0.5rem 0;
        border-bottom: 1px solid var(--border-subtle, #efeff1);
    }
    .bundle > div:last-child {
        border-bottom: none;
    }
    .bundle dt {
        color: var(--fg-subtle, #6b7280);
    }
    .bundle dd {
        margin: 0;
        text-align: right;
        font-weight: 600;
    }
</style>
