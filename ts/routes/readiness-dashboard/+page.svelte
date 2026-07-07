<!--
Copyright: Ankitects Pty Ltd and contributors
License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
-->
<script lang="ts">
    import { onMount } from "svelte";
    import { slide } from "svelte/transition";

    import { computeReadiness, getMasteryState } from "@generated/backend";
    import type { MasteryState, ReadinessResult } from "@generated/anki/speedrun_pb";
    import { MIN_PERF_QUESTIONS, type MetricId, wilsonInterval } from "../metrics/lib";
    import Explainer from "../metrics/Explainer.svelte";
    import { masteryInputs } from "../study-map/lib";
    import ReadinessBundle from "./ReadinessBundle.svelte";

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

    // Official SOA P section weights (range midpoints) so coverage is weighted:
    // skipping a high-weight section can't read as "covered".
    const UNIT_WEIGHTS = [
        { unitId: "general", weight: 26.5 },
        { unitId: "univariate", weight: 47 },
        { unitId: "multivariate", weight: 26.5 },
    ];

    let result: ReadinessResult | null = null;
    // Per-subtopic practice-test performance, read from the SAME mastery state the
    // study-map and metrics pages use. Kept separate from readiness: it drives the
    // Performance card independently of the readiness give-up rule.
    let mastery: MasteryState | null = null;
    let loadError = "";

    onMount(async () => {
        const [readinessRes, masteryRes] = await Promise.allSettled([
            computeReadiness({
                expectedSubtopics: EXPECTED_SUBTOPICS,
                units: UNIT_WEIGHTS,
            }),
            getMasteryState(masteryInputs()),
        ]);
        if (readinessRes.status === "fulfilled") {
            result = readinessRes.value;
        } else {
            loadError = String(readinessRes.reason);
        }
        // A mastery failure is non-fatal: the Performance card falls back to its
        // honest abstain and the readiness report still renders.
        if (masteryRes.status === "fulfilled") {
            mastery = masteryRes.value;
        }
    });

    $: noScore = result?.value.case === "noScore" ? result.value.value : null;
    $: score = result?.value.case === "score" ? result.value.value : null;
    // Memory signal (with a range), independent of the readiness give-up rule.
    $: memoryRecall = result?.memoryRecall ?? null;
    $: gradedReviews = noScore?.gradedReviews ?? 0;
    // Memory detail line, kept out of the signals array to avoid a nested
    // ternary: reviewed-card count once we have a measured band, else the
    // graded-review count, else nothing studied yet.
    $: memoryDetail = ((): string => {
        if (memoryRecall?.hasData) {
            return `${memoryRecall.reviewedCards} cards reviewed · 10th-90th pct range`;
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

    // Performance signal (with a range), measured per subtopic from graded
    // practice tests and independent of the readiness give-up rule. Pool the same
    // per-subtopic counts the study-map / metrics pages read from the mastery
    // state: overall accuracy = total correct / total graded questions across
    // MEASURED subtopics (perf_questions > 0). Never blended into Memory.
    $: perf = ((): {
        questions: number;
        correct: number;
        withData: number;
        mastered: number;
        accuracy: number;
    } => {
        const subs = mastery?.subtopics ?? [];
        let questions = 0;
        let correct = 0;
        let withData = 0;
        let mastered = 0;
        for (const s of subs) {
            questions += s.perfQuestions;
            correct += s.perfCorrect;
            if (s.perfQuestions > 0) {
                withData += 1;
            }
            if (s.performanceMastered) {
                mastered += 1;
            }
        }
        return {
            questions,
            correct,
            withData,
            mastered,
            accuracy: questions > 0 ? correct / questions : 0,
        };
    })();
    // Honesty floor: headline an overall Performance number only with at least one
    // measured subtopic AND at least the engine's per-subtopic sample floor of
    // graded questions (MIN_PERF_QUESTIONS). Below that the card abstains rather
    // than report a proportion from one or two lucky answers.
    $: perfMeasured = perf.withData > 0 && perf.questions >= MIN_PERF_QUESTIONS;
    // 95% Wilson interval on the pooled proportion, the same band math the
    // readiness engine uses, so Performance is shown WITH a range like the other
    // two cards (never a bare point).
    $: perfBand = perfMeasured ? wilsonInterval(perf.correct, perf.questions) : null;
    // Honest detail line: measured counts + band type when scored, else progress
    // toward the sample floor (or nothing practiced yet).
    $: perfDetail = ((): string => {
        if (perfMeasured) {
            return `${perf.correct}/${perf.questions} correct across ${perf.withData} subtopics · 95% Wilson`;
        }
        if (perf.questions > 0) {
            return `${perf.questions}/${MIN_PERF_QUESTIONS} graded questions so far`;
        }
        return "no graded questions yet";
    })();

    function pct(x: number): string {
        return `${Math.round(x * 100)}%`;
    }

    // The three signals, shown side by side and never blended into one number.
    // Each is measured from its own source (Memory from FSRS, Performance from
    // graded practice tests, Readiness from the P(pass) model) and abstains
    // honestly on its own data rather than showing a fabricated value.
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
                ? `${pct(memoryRecall.point)} (${pct(memoryRecall.low)}-${pct(memoryRecall.high)})`
                : "Not yet scored",
            detail: memoryDetail,
            source: "FSRS retrievability",
        },
        {
            id: "performance",
            name: "Performance",
            question: "Can you solve a new, exam-style question?",
            state: perfMeasured ? "score" : "pending",
            value:
                perfMeasured && perfBand
                    ? `${pct(perf.accuracy)} (${pct(perfBand.low)}-${pct(perfBand.high)})`
                    : "Not yet measured",
            detail: perfDetail,
            source: "Performance model",
        },
        {
            id: "readiness",
            name: "Readiness",
            question: "Would you pass today, and how sure are we?",
            state: score ? "score" : "giveup",
            value: score
                ? `${score.point.toFixed(1)} (${score.low.toFixed(1)}-${score.high.toFixed(1)})`
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

        <section class="panel bundle-panel">
            <ReadinessBundle {result} />
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
        font-size: var(--sr-text-base);
        line-height: 1.5;
    }
    /* Header: loud chrome (the numbers below stay calm). */
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
        font-size: var(--sr-text-xs);
        font-weight: 700;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        color: var(--sr-accent);
    }

    /* Generic panel is CALM by design: opaque, high-contrast, sober frame, since
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

    /* Three-signal row: bold frames, but the VALUE stays calm + high-contrast. */
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
    /* "How is this calculated?" is the transparency method folded in from the
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
        font-size: var(--sr-text-sm);
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
        font-size: var(--sr-text-sm);
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
        font-size: var(--sr-text-sm);
        color: var(--fg-subtle);
    }
    .signal .source {
        margin: 0.7rem 0 0;
        font-family: var(--sr-font-body);
        font-size: var(--sr-text-xs);
        font-weight: 700;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: var(--signal-color);
    }

    /* Honesty bundle: a quiet panel with a plum top accent; the data list itself
       lives in the reusable ReadinessBundle component. */
    .bundle-panel {
        border: 1px solid var(--border);
        box-shadow:
            inset 0 3px 0 0 var(--sr-quinary),
            var(--sr-shadow);
    }
</style>
