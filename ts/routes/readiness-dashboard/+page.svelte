<!--
Copyright: Ankitects Pty Ltd and contributors
License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
-->
<script lang="ts">
    import { onMount } from "svelte";

    import { computeReadiness } from "@generated/backend";
    import type { ReadinessResult } from "@generated/anki/speedrun_pb";

    // Mirrors pylib/anki/speedrun/exam_p_topics.json. A future RPC will serve the
    // syllabus so there is a single source; hardcoded here for the stub.
    const EXPECTED_SUBTOPICS = [
        "subtopic::general::sample_spaces",
        "subtopic::general::combinatorics",
        "subtopic::general::conditional",
        "subtopic::general::independence",
        "subtopic::general::bayes",
        "subtopic::univariate::discrete_common",
        "subtopic::univariate::continuous_common",
        "subtopic::univariate::expectation_variance",
        "subtopic::univariate::mgf",
        "subtopic::univariate::transformations",
        "subtopic::multivariate::joint_distributions",
        "subtopic::multivariate::marginal_conditional",
        "subtopic::multivariate::covariance_correlation",
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
    $: nextAction = noScore?.nextBestAction ?? score?.nextBestAction ?? "—";

    function pct(x: number): string {
        return `${Math.round(x * 100)}%`;
    }
</script>

<div class="readiness">
    <header>
        <h1>Exam readiness — SOA Exam P</h1>
        <p class="subtitle">
            Three separate signals, never blended: <b>memory</b>
            (can you recall the fact),
            <b>performance</b>
            (can you solve a new exam-style question), and
            <b>readiness</b>
            (would you pass, and how sure are we).
        </p>
    </header>

    {#if loadError}
        <div class="card error">
            <h2>Couldn't compute readiness</h2>
            <p>{loadError}</p>
        </div>
    {:else if result === null}
        <div class="card muted">Computing readiness…</div>
    {:else if noScore}
        <div class="card giveup">
            <div class="badge">Not enough data yet</div>
            <p class="reason">{noScore.reason}</p>
            <div class="metrics">
                <div class="metric">
                    <span class="label">Graded reviews</span>
                    <span class="value">{noScore.gradedReviews} / 200</span>
                    <span class="hint">{noScore.reviewsNeeded} more needed</span>
                </div>
                <div class="metric">
                    <span class="label">Syllabus coverage</span>
                    <span class="value">{pct(coveragePct)}</span>
                    <span class="hint">need ≥ 50%</span>
                </div>
            </div>
            <div class="next-action">
                <span class="label">Single best next action</span>
                <p>{noScore.nextBestAction}</p>
            </div>
        </div>
    {:else if score}
        <div class="card score">
            <div class="point">
                {score.point.toFixed(1)}
                <span class="range">
                    ({score.low.toFixed(1)}–{score.high.toFixed(1)})
                </span>
            </div>
            <p>
                Coverage {pct(score.coveragePct)} · confidence {pct(score.confidence)}
            </p>
            <p class="next">{score.nextBestAction}</p>
        </div>
    {/if}

    <section class="honesty">
        <h2>Every readiness report must show all of this</h2>
        <p class="note">
            The give-up rule is enforced in the Rust engine: below ≥ 200 graded reviews <b
            >
                and
            </b>
            ≥ 50% coverage, no number is shown. Fields below stay blank ("—") until the memory
            and performance models are calibrated — we never fabricate a number.
        </p>
        <ul class="bundle">
            <li>
                <span>Point estimate</span>
                <b>{score ? score.point.toFixed(1) : "—"}</b>
            </li>
            <li>
                <span>Likely range</span>
                <b>
                    {score ? `${score.low.toFixed(1)}–${score.high.toFixed(1)}` : "—"}
                </b>
            </li>
            <li>
                <span>Syllabus covered</span>
                <b>{pct(coveragePct)}</b>
            </li>
            <li>
                <span>How sure (confidence)</span>
                <b>{score ? pct(score.confidence) : "—"}</b>
            </li>
            <li>
                <span>Last updated</span>
                <b>
                    {score
                        ? new Date(Number(score.updatedAt) * 1000).toLocaleString()
                        : "—"}
                </b>
            </li>
            <li>
                <span>Main reasons</span>
                <b>{score && score.reasons.length ? score.reasons.join("; ") : "—"}</b>
            </li>
            <li>
                <span>Single best next action</span>
                <b>{nextAction}</b>
            </li>
        </ul>
    </section>
</div>

<style>
    .readiness {
        max-width: 720px;
        margin: 0 auto;
        padding: 1.5rem;
        color: var(--fg, #222);
    }
    header h1 {
        margin: 0 0 0.25rem;
        font-size: 1.6rem;
    }
    .subtitle {
        margin: 0 0 1.25rem;
        opacity: 0.8;
        line-height: 1.4;
    }
    .card {
        border: 1px solid var(--border, #d0d0d0);
        border-radius: 12px;
        padding: 1.25rem 1.5rem;
        margin-bottom: 1.5rem;
        background: var(--canvas-elevated, #fafafa);
    }
    .card.muted {
        opacity: 0.7;
    }
    .card.error {
        border-color: #d9534f;
    }
    .giveup .badge {
        display: inline-block;
        background: #e0a800;
        color: #1c1c1c;
        font-weight: 600;
        border-radius: 999px;
        padding: 0.2rem 0.75rem;
        font-size: 0.85rem;
        margin-bottom: 0.75rem;
    }
    .giveup .reason {
        font-size: 1.05rem;
        margin: 0 0 1rem;
    }
    .metrics {
        display: flex;
        gap: 1.5rem;
        flex-wrap: wrap;
        margin-bottom: 1rem;
    }
    .metric {
        display: flex;
        flex-direction: column;
    }
    .metric .label,
    .next-action .label {
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.03em;
        opacity: 0.65;
    }
    .metric .value {
        font-size: 1.6rem;
        font-weight: 700;
    }
    .metric .hint {
        font-size: 0.8rem;
        opacity: 0.7;
    }
    .next-action {
        border-top: 1px solid var(--border, #e0e0e0);
        padding-top: 0.75rem;
    }
    .next-action p {
        margin: 0.25rem 0 0;
        font-size: 1.05rem;
        font-weight: 600;
    }
    .card.score .point {
        font-size: 2.5rem;
        font-weight: 800;
    }
    .card.score .range {
        font-size: 1rem;
        font-weight: 400;
        opacity: 0.7;
    }
    .honesty h2 {
        font-size: 1.15rem;
    }
    .honesty .note {
        opacity: 0.8;
        line-height: 1.4;
        font-size: 0.92rem;
    }
    .bundle {
        list-style: none;
        padding: 0;
        margin: 0.5rem 0 0;
    }
    .bundle li {
        display: flex;
        justify-content: space-between;
        gap: 1rem;
        padding: 0.5rem 0;
        border-bottom: 1px solid var(--border, #eee);
    }
    .bundle li span {
        opacity: 0.75;
    }
    .bundle li b {
        text-align: right;
    }
</style>
