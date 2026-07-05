<!--
Copyright: Ankitects Pty Ltd and contributors
License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
-->
<script lang="ts">
    import { onMount } from "svelte";
    import { slide } from "svelte/transition";

    import { computeReadiness } from "@generated/backend";
    import type { ReadinessResult } from "@generated/anki/speedrun_pb";
    import type { MetricId } from "../metrics/lib";
    import Explainer from "../metrics/Explainer.svelte";
    import { TAXONOMY, subtopicTag } from "../study-map/lib";

    // The full method behind every number lives in a collapsible "How is this
    // calculated?" panel on THIS page (folded in from the old standalone
    // transparency route, so there is one honesty surface, not a separate tab).
    // Each signal card is clickable: it opens that panel anchored to the signal.
    let explainerOpen = false;
    let explainerAnchor: MetricId | null = null;
    function openMetric(id: MetricId): void {
        explainerAnchor = id;
        explainerOpen = true;
    }
    function toggleExplainer(): void {
        explainerOpen = !explainerOpen;
        if (!explainerOpen) {
            explainerAnchor = null;
        }
    }
    function onCardKey(e: KeyboardEvent, id: MetricId): void {
        if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            openMetric(id);
        }
    }

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

    // The readiness engine can only put the raw subtopic TAG into its
    // next-best-action sentence (the human names live in the syllabus/TAXONOMY on
    // the client, not in Rust). Swap any tag token for its name so the honesty
    // bundle reads "Focus your weakest area next: Linear combinations (71% correct
    // so far)…" instead of "subtopic::multivariate::linear_combinations". Display
    // only — it never changes the measured number.
    const SUBTOPIC_NAME = new Map<string, string>(
        TAXONOMY.flatMap((u) =>
            u.subtopics.map(
                (s) => [subtopicTag(u.id, s.id), s.name] as [string, string],
            ),
        ),
    );
    function humanizeAction(text: string): string {
        return text.replace(
            /subtopic::[a-z0-9_]+::[a-z0-9_]+/gi,
            (tag) => SUBTOPIC_NAME.get(tag) ?? tag,
        );
    }

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
    // Memory signal (with a range), independent of the readiness give-up rule.
    $: memoryRecall = result?.memoryRecall ?? null;
    $: coveragePct = noScore?.coveragePct ?? score?.coveragePct ?? 0;
    $: gradedReviews = noScore?.gradedReviews ?? 0;
    $: nextAction = humanizeAction(
        noScore?.nextBestAction ?? score?.nextBestAction ?? "—",
    );
    // Memory detail line, kept out of the signals array to avoid a nested
    // ternary: reviewed-card count once we have a measured band, else the
    // graded-review count, else nothing studied yet.
    $: memoryDetail = ((): string => {
        if (memoryRecall?.hasData) {
            return `${memoryRecall.reviewedCards} cards reviewed · 10th–90th pct range`;
        }
        if (gradedReviews > 0) {
            return `${gradedReviews} graded reviews on file`;
        }
        return "no reviews yet";
    })();
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
        id: MetricId;
        name: string;
        question: string;
        state: SignalState;
        value: string;
        detail: string;
        source: string;
    }

    $: signals = [
        {
            id: "memory",
            name: "Memory",
            question: "Can you recall the fact right now?",
            state: memoryRecall?.hasData ? "score" : "pending",
            value: memoryRecall?.hasData
                ? `${pct(memoryRecall.point)} (${pct(memoryRecall.low)}–${pct(memoryRecall.high)})`
                : "Not yet scored",
            detail: memoryDetail,
            source: "FSRS retrievability",
        },
        {
            id: "performance",
            name: "Performance",
            question: "Can you solve a new, exam-style question?",
            state: "pending",
            value: "Not yet measured",
            detail: "needs exam-style items",
            source: "Performance model",
        },
        {
            id: "readiness",
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
                <div
                    class="signal {s.state}"
                    role="button"
                    tabindex="0"
                    aria-label={`${s.name}: ${s.value}. Open how it's calculated.`}
                    on:click={() => openMetric(s.id)}
                    on:keydown={(e) => onCardKey(e, s.id)}
                >
                    <div class="signal-head">
                        <span class="dot" aria-hidden="true"></span>
                        <h2>{s.name}</h2>
                    </div>
                    <p class="question">{s.question}</p>
                    <p class="value">{s.value}</p>
                    <p class="detail">{s.detail}</p>
                    <p class="source">{s.source}</p>
                    <p class="explain-link" aria-hidden="true">
                        What is this? · How it's calculated →
                    </p>
                </div>
            {/each}
        </section>

        <section class="how-it-works">
            <button
                type="button"
                class="explainer-toggle"
                aria-expanded={explainerOpen}
                on:click={toggleExplainer}
            >
                <span>
                    {explainerOpen
                        ? "Hide how these are calculated"
                        : "How is this calculated?"}
                </span>
                <span class="chevron" class:open={explainerOpen} aria-hidden="true">
                    ▾
                </span>
            </button>
            {#if explainerOpen}
                <div class="explainer-panel" transition:slide>
                    <Explainer anchor={explainerAnchor} />
                </div>
            {/if}
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
                    <p>{humanizeAction(noScore.nextBestAction)}</p>
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
                    <p>{humanizeAction(score.nextBestAction)}</p>
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
        position: relative;
        z-index: 0;
        max-width: 940px;
        margin: 0 auto;
        padding: 2rem 1.5rem 4rem;
        color: var(--fg);
        font-family: var(--sr-font-body);
        font-size: 15px;
        line-height: 1.5;
    }
    /* Header — loud chrome (the numbers below stay calm). */
    header {
        position: relative;
        z-index: 1;
        margin-bottom: 1.75rem;
    }
    header h1 {
        margin: 0;
        font-family: var(--sr-font-heading);
        font-size: clamp(2rem, 4.5vw, 2.9rem);
        font-weight: 600;
        line-height: 1.05;
        letter-spacing: -0.01em;
        color: var(--fg);
    }
    header .exam {
        margin: 0.6rem 0 0;
        font-family: var(--sr-font-body);
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        color: var(--sr-accent);
    }
    header .subtitle {
        margin: 0.6rem 0 0;
        color: var(--fg-subtle);
        font-size: 0.95rem;
    }

    /* Generic panel — CALM by design: opaque, high-contrast, sober frame, since
       these carry measured numbers (honesty core, not loud chrome). */
    .panel {
        position: relative;
        z-index: 1;
        border: 2px solid var(--border);
        border-radius: var(--sr-radius-lg);
        padding: 1.6rem 1.7rem;
        margin-bottom: 1.4rem;
        background: var(--canvas-elevated);
        box-shadow: var(--sr-shadow);
    }
    .panel.muted {
        color: var(--fg-subtle);
    }
    .panel.error {
        border-color: var(--sr-quaternary);
        border-width: var(--sr-border);
    }
    .panel-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.75rem;
        margin-bottom: 0.6rem;
    }
    .panel-head h2 {
        margin: 0;
        font-family: var(--sr-font-heading);
        font-size: 1.2rem;
        font-weight: 600;
    }

    /* Three-signal row — bold frames, but the VALUE stays calm + high-contrast. */
    .signals {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 1rem;
        margin-bottom: 1.4rem;
    }
    .signal {
        position: relative;
        z-index: 1;
        display: block;
        width: 100%;
        text-align: left;
        border: 1px solid var(--border);
        border-radius: var(--sr-radius);
        padding: 1.2rem 1.25rem 1.3rem;
        background: var(--canvas-elevated);
        /* 3px top-accent stripe (inset shadow so it tucks into the rounded
           corners); the signal colour reads the section identity. */
        box-shadow:
            inset 0 3px 0 0 var(--signal-color, var(--sr-pending)),
            var(--sr-shadow-sm);
        cursor: pointer;
        transition:
            transform 0.15s ease,
            box-shadow 0.2s ease,
            border-color 0.2s ease;
    }
    /* Clickable affordance: a calm lift, never a glow. */
    .signal:hover {
        transform: translateY(-2px);
        box-shadow:
            inset 0 3px 0 0 var(--signal-color, var(--sr-pending)),
            var(--sr-shadow);
        border-color: var(--signal-color, var(--sr-pending));
    }
    .signal:active {
        transform: translateY(0);
    }
    .signal:focus-visible {
        outline: 2px solid var(--sr-focus);
        outline-offset: 2px;
    }
    .explain-link {
        margin: 0.85rem 0 0;
        font-family: var(--sr-font-body);
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.03em;
        color: var(--sr-accent);
    }
    /* "How is this calculated?" — the transparency method folded in from the
       old standalone metrics page, revealed inline (not a separate tab). */
    .how-it-works {
        margin: 1.25rem 0 0;
    }
    .explainer-toggle {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        border: 1px solid var(--border);
        background: var(--canvas-elevated);
        color: var(--sr-accent);
        font-family: var(--sr-font-body);
        font-weight: 700;
        font-size: 0.8rem;
        padding: 0.5rem 0.95rem;
        border-radius: var(--sr-radius-pill);
        cursor: pointer;
        transition:
            border-color 0.2s ease,
            background 0.2s ease;
    }
    .explainer-toggle:hover {
        border-color: var(--sr-accent);
        background: var(--sr-accent-weak);
    }
    .explainer-toggle:focus-visible {
        outline: 2px solid var(--sr-focus);
        outline-offset: 2px;
    }
    .chevron {
        transition: transform 0.2s ease;
    }
    .chevron.open {
        transform: rotate(180deg);
    }
    .explainer-panel {
        margin-top: 0.75rem;
        border: 1px solid var(--border);
        border-radius: var(--sr-radius-lg);
        background: var(--canvas-elevated);
        overflow: hidden;
    }
    .signal.pending {
        --signal-color: var(--sr-pending);
    }
    .signal.giveup {
        --signal-color: var(--sr-progress);
    }
    .signal.score {
        --signal-color: var(--sr-mastered);
    }
    .signal-head {
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    .signal-head h2 {
        margin: 0;
        font-family: var(--sr-font-heading);
        font-size: 1.05rem;
        font-weight: 600;
    }
    .dot {
        width: 10px;
        height: 10px;
        border-radius: 50%;
        background: var(--signal-color, var(--sr-pending));
        flex: 0 0 auto;
    }
    .signal .question {
        margin: 0.5rem 0 0.85rem;
        font-size: 0.82rem;
        color: var(--fg-subtle);
        min-height: 2.2em;
    }
    .signal .value {
        margin: 0;
        /* Measured number: clean body font (never the bubbly display font) with
           tabular figures, so the score reads as serious data. */
        font-family: var(--sr-font-body);
        font-variant-numeric: tabular-nums;
        font-size: 1.3rem;
        font-weight: 700;
        line-height: 1.1;
        color: var(--fg);
    }
    .signal .detail {
        margin: 0.25rem 0 0;
        font-size: 0.8rem;
        color: var(--fg-subtle);
    }
    .signal .source {
        margin: 0.7rem 0 0;
        font-family: var(--sr-font-body);
        font-size: 0.66rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: var(--signal-color);
    }

    /* Readiness detail. The ABSTAIN panel wears an honest amber frame (we're
       withholding) — never a celebratory green/glow. When a real score exists
       the panel uses a calm cyan frame. Numbers inside stay white + high-contrast. */
    .detail-panel:not(.score-panel) {
        border: 1px solid var(--border);
        box-shadow:
            inset 0 3px 0 0 var(--sr-progress),
            var(--sr-shadow);
    }
    .score-panel {
        border: 1px solid var(--border);
        box-shadow:
            inset 0 3px 0 0 var(--sr-mastered),
            var(--sr-shadow);
    }
    .badge {
        display: inline-block;
        border: 1px solid var(--sr-progress);
        color: var(--sr-progress);
        font-family: var(--sr-font-body);
        font-weight: 700;
        font-size: 0.7rem;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        border-radius: var(--sr-radius-pill);
        padding: 0.25rem 0.7rem;
        white-space: nowrap;
    }
    .badge.ok {
        border-color: var(--sr-mastered);
        color: var(--sr-mastered);
    }
    .reason {
        margin: 0 0 1rem;
        color: var(--fg);
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
        gap: 0.3rem;
    }
    .label {
        font-family: var(--sr-font-body);
        font-size: 0.7rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: var(--fg-subtle);
    }
    .metric-value {
        font-family: var(--sr-font-heading);
        font-size: 1.6rem;
        font-weight: 600;
        line-height: 1.05;
        color: var(--fg);
    }
    .bar {
        height: 8px;
        border-radius: var(--sr-radius-pill);
        background: var(--canvas-inset);
        border: 1px solid var(--border);
        overflow: hidden;
    }
    .bar-fill {
        display: block;
        height: 100%;
        background: var(--sr-progress);
        border-radius: var(--sr-radius-pill);
    }
    .metric .hint,
    .score-panel .hint {
        font-size: 0.8rem;
        color: var(--fg-subtle);
    }
    .next-action {
        border-top: 1px solid var(--border);
        padding-top: 0.85rem;
        margin-top: 0.25rem;
    }
    .next-action .label {
        color: var(--sr-accent);
    }
    .next-action p {
        margin: 0.3rem 0 0;
        font-weight: 700;
        font-size: 1.02rem;
    }
    /* The score itself: large + white + calm. No glow, no pulse — a measured
       number shown with its range, never dressed up. */
    .score-panel .point {
        /* Measured readiness estimate: clean body font + tabular figures, never
           the bubbly display font — the number must read as data, not decoration. */
        font-family: var(--sr-font-body);
        font-variant-numeric: tabular-nums;
        font-size: 2.6rem;
        font-weight: 800;
        line-height: 1;
        color: var(--fg);
    }
    .score-panel .range {
        font-family: var(--sr-font-body);
        font-size: 1.1rem;
        font-weight: 600;
        color: var(--fg-subtle);
    }
    .pass-prob {
        margin: 0.5rem 0 0;
        font-size: 1rem;
    }
    .pass-prob b {
        font-size: 1.15rem;
    }

    /* Honesty bundle — a quiet panel with a plum top accent; the data list stays
       high-contrast + readable. */
    .bundle-panel {
        border: 1px solid var(--border);
        box-shadow:
            inset 0 3px 0 0 var(--sr-quinary),
            var(--sr-shadow);
    }
    .bundle-panel h2 {
        margin: 0 0 0.5rem;
        font-family: var(--sr-font-heading);
        font-size: 1.2rem;
        font-weight: 600;
    }
    .note {
        margin: 0 0 0.9rem;
        color: var(--fg-subtle);
        font-size: 0.88rem;
        line-height: 1.55;
    }
    .bundle {
        margin: 0;
    }
    .bundle > div {
        display: flex;
        justify-content: space-between;
        gap: 1rem;
        padding: 0.6rem 0;
        border-bottom: 1px solid var(--border-subtle);
    }
    .bundle > div:last-child {
        border-bottom: none;
    }
    .bundle dt {
        color: var(--fg-subtle);
        font-family: var(--sr-font-body);
        font-size: 0.82rem;
        font-weight: 600;
    }
    .bundle dd {
        margin: 0;
        text-align: right;
        font-weight: 700;
        color: var(--fg);
    }
</style>
