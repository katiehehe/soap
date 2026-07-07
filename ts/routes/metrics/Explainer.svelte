<!--
Copyright: Ankitects Pty Ltd and contributors
License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
-->
<script lang="ts">
    import { onMount } from "svelte";

    import { computeReadiness, getMasteryState } from "@generated/backend";
    import type { MasteryState, ReadinessResult } from "@generated/anki/speedrun_pb";

    // Reuse the SAME taxonomy + weights the map/readiness screens send, so the
    // live inputs shown here match the numbers the engine computes elsewhere.
    import { masteryInputs } from "../study-map/lib";
    import {
        METRIC_IDS,
        METRIC_LABELS,
        MIN_COVERAGE,
        MIN_GRADED_REVIEWS,
        MIN_PERF_ACCURACY,
        MIN_PERF_QUESTIONS,
        MIN_PRACTICE_QUESTIONS,
        PASS_PROPORTION,
        PASS_SCALED,
        SCALE_MAX,
        type MetricId,
    } from "./lib";

    // Embedded in the readiness dashboard's collapsible "How is this calculated?"
    // panel. The parent passes the signal to reveal (e.g. after a click on a
    // readiness signal card); it selects that signal's tab, so only that one
    // explanation shows.
    export let anchor: MetricId | null = null;

    // One signal's explanation is shown at a time, as a tab. Default to the
    // parent's anchor (a clicked signal card) or Memory.
    let active: MetricId = anchor ?? "memory";

    // Per-signal accent, matching the readiness dashboard's signal colours
    // (memory = accent, performance = quaternary, readiness = quinary).
    const TAB_ACCENT: Record<MetricId, string> = {
        memory: "var(--sr-accent)",
        performance: "var(--sr-quaternary)",
        readiness: "var(--sr-quinary)",
    };

    let readiness: ReadinessResult | null = null;
    let mastery: MasteryState | null = null;

    function pct(x: number): string {
        return `${Math.round(x * 100)}%`;
    }
    function one(x: number): string {
        return x.toFixed(1);
    }

    // Readiness is a oneof: never a bare number below the give-up rule.
    $: noScore = readiness?.value.case === "noScore" ? readiness.value.value : null;
    $: score = readiness?.value.case === "score" ? readiness.value.value : null;
    // Memory (with a range), computed independently of the readiness give-up rule.
    $: memory = readiness?.memoryRecall ?? null;
    $: coveragePct = noScore?.coveragePct ?? score?.coveragePct ?? 0;
    // graded_review_count is only carried on the NoScore path; once a score
    // exists the review gate is met by definition (>= 200).
    $: gradedReviews = noScore?.gradedReviews ?? null;

    // Performance is MEASURED per subtopic (never blended into one number). We
    // summarise the measured counts: total graded practice questions, overall
    // practice accuracy, and how many subtopics clear the performance gate. The
    // summed perf-questions equal the readiness practice-question count (both are
    // written from the same graded tests), so we reuse it for the give-up row.
    $: perf = ((): {
        questions: number;
        correct: number;
        mastered: number;
        withData: number;
        accuracy: number;
    } => {
        const subs = mastery?.subtopics ?? [];
        let questions = 0;
        let correct = 0;
        let mastered = 0;
        let withData = 0;
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
            mastered,
            withData,
            accuracy: questions > 0 ? correct / questions : 0,
        };
    })();
    $: practiceQuestions = perf.questions;

    // Give-up gate status, from the same three thresholds the engine enforces.
    $: reviewsMet = score !== null || (gradedReviews ?? 0) >= MIN_GRADED_REVIEWS;
    $: coverageMet = coveragePct >= MIN_COVERAGE;
    $: practiceMet = practiceQuestions >= MIN_PRACTICE_QUESTIONS;

    // Roving-tabindex keyboard support for the tablist: arrows/Home/End move
    // focus and change the shown signal (selection follows focus, the standard
    // tabs pattern).
    function onTabKey(e: KeyboardEvent, id: MetricId): void {
        const i = METRIC_IDS.indexOf(id);
        let next: number | null = null;
        if (e.key === "ArrowRight" || e.key === "ArrowDown") {
            next = (i + 1) % METRIC_IDS.length;
        } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
            next = (i - 1 + METRIC_IDS.length) % METRIC_IDS.length;
        } else if (e.key === "Home") {
            next = 0;
        } else if (e.key === "End") {
            next = METRIC_IDS.length - 1;
        }
        if (next === null) {
            return;
        }
        e.preventDefault();
        active = METRIC_IDS[next];
        document.getElementById(`tab-${active}`)?.focus();
    }

    onMount(async () => {
        try {
            const inputs = masteryInputs();
            [readiness, mastery] = await Promise.all([
                computeReadiness({
                    expectedSubtopics: inputs.expectedSubtopics,
                    units: inputs.units,
                }),
                getMasteryState(inputs),
            ]);
        } catch (_err) {
            // Live inputs are a bonus: the definitions render without the engine.
        }
    });

    // A parent-driven anchor change (a clicked signal card) selects that tab.
    $: if (anchor) {
        active = anchor;
    }
</script>

<div class="metrics">
    <header class="page-head">
        <div class="tabs" role="tablist" aria-label="Choose a signal to explain">
            {#each METRIC_IDS as id}
                <button
                    type="button"
                    role="tab"
                    id={`tab-${id}`}
                    class="tab"
                    class:active={active === id}
                    style="--tab-accent:{TAB_ACCENT[id]}"
                    aria-selected={active === id}
                    aria-controls={`panel-${id}`}
                    tabindex={active === id ? 0 : -1}
                    on:click={() => (active = id)}
                    on:keydown={(e) => onTabKey(e, id)}
                >
                    {METRIC_LABELS[id]}
                </button>
            {/each}
        </div>
    </header>

    <!-- ================= MEMORY ================= -->
    <div
        id="panel-memory"
        class="card memory"
        role="tabpanel"
        aria-labelledby="tab-memory"
        tabindex="0"
        hidden={active !== "memory"}
    >
        <div class="card-head">
            <p class="metric-eyebrow">Signal 1 · Memory</p>
            <h2>Can you recall this fact right now?</h2>
            <!-- Named source, kept for traceability but not rendered in the UI:
            <p class="source-line">
                Source: <b>FSRS retrievability</b>, Anki's spaced-repetition
                model, in the shared Rust engine.
            </p>
            -->
        </div>

        <div class="live {memory?.hasData ? 'measured' : 'withheld'}">
            <span class="badge">
                {memory?.hasData ? "Measured" : "Withheld: no reviews yet"}
            </span>
            {#if memory?.hasData}
                <p class="live-value">
                    {pct(memory.point)}
                    <span class="live-range">
                        ({pct(memory.low)}-{pct(memory.high)})
                    </span>
                </p>
                <p class="live-note">
                    Mean P(recall today) across {memory.reviewedCards} reviewed cards · range
                    is the 10th-90th percentile.
                </p>
            {:else}
                <p class="live-value muted">Not yet scored</p>
                <p class="live-note">
                    No syllabus card has a graded review, so Memory shows nothing rather
                    than a fabricated number.
                </p>
            {/if}
        </div>

        <div class="explain">
            <div class="block">
                <p class="k">What data goes in</p>
                <p>
                    Your review history, per card: the grades and timing FSRS uses to
                    fit each card's forgetting curve. Only cards tagged to the syllabus
                    that you have actually reviewed count.
                </p>
            </div>
            <div class="block">
                <p class="k">How it is calculated</p>
                <p>
                    For every reviewed syllabus card the engine reads FSRS's predicted
                    probability of recall <i>today</i>
                    . The point value is the
                    <b>mean</b>
                    of those per-card probabilities; the range is their
                    <b>10th-90th percentile</b>
                    , so you see the spread, not just an average. It never mixes in practice-test
                    results.
                </p>
                <p class="formula">
                    point = mean(P(recall)) · band = [P10, P90] over reviewed cards
                </p>
            </div>
            <div class="block">
                <p class="k">Data thresholds</p>
                <p>
                    Abstains until at least one syllabus card has a graded review (
                    <code>has_data = false</code>
                    when empty). No reviews → no number, by construction.
                </p>
            </div>
        </div>
        <!-- Engine traceability, kept in source but not rendered in the UI:
        <p class="engine-src">
            Mirrors <code>memory_recall</code> in rslib/src/speedrun/mastery.rs,
            surfaced by <code>compute_readiness</code>.
        </p>
        -->
    </div>

    <!-- ================= PERFORMANCE ================= -->
    <div
        id="panel-performance"
        class="card performance"
        role="tabpanel"
        aria-labelledby="tab-performance"
        tabindex="0"
        hidden={active !== "performance"}
    >
        <div class="card-head">
            <p class="metric-eyebrow">Signal 2 · Performance</p>
            <h2>Can you solve a new, exam-style question?</h2>
            <!-- Named source, kept for traceability but not rendered in the UI:
            <p class="source-line">
                Source: <b>graded multiple-choice practice tests</b> (procedure,
                not recall).
            </p>
            -->
        </div>

        <div class="live {perf.withData > 0 ? 'measured' : 'withheld'}">
            <span class="badge">
                {perf.withData > 0
                    ? "Measured (per subtopic)"
                    : "Withheld: no graded questions yet"}
            </span>
            {#if perf.withData > 0}
                <p class="live-value">
                    {pct(perf.accuracy)}
                    <span class="live-range">
                        ({perf.correct}/{perf.questions} questions)
                    </span>
                </p>
                <p class="live-note">
                    Across {perf.withData} practiced subtopics · {perf.mastered}
                    at the mastery gate (≥ {MIN_PERF_QUESTIONS} questions and ≥ {pct(
                        MIN_PERF_ACCURACY,
                    )}).
                </p>
            {:else}
                <p class="live-value muted">Not yet measured</p>
                <p class="live-note">
                    No graded practice questions on file, so Performance abstains.
                </p>
            {/if}
        </div>

        <div class="explain">
            <div class="block">
                <p class="k">What data goes in</p>
                <p>
                    Correct / total on <b>disguised, parameterized</b>
                    A-E questions, tallied
                    <b>per subtopic</b>
                    . The numbers regenerate on each attempt, so this measures whether you
                    can run the procedure, not whether you recognise a memorised cue.
                </p>
            </div>
            <div class="block">
                <p class="k">How it is calculated</p>
                <p>
                    Per subtopic, performance accuracy = correct ÷ graded questions. A
                    subtopic reads <b>mastered</b>
                    once it has ≥ {MIN_PERF_QUESTIONS}
                    graded questions
                    <b>and</b>
                    ≥ {pct(MIN_PERF_ACCURACY)} correct ("strong"). Performance is kept
                    <b>separate</b>
                    from Memory: it can satisfy a prerequisite in the guided map, but it never
                    moves the memory gate and the two are never averaged together.
                </p>
                <p class="formula">
                    accuracy = correct ÷ questions · mastered ⇔ questions ≥ {MIN_PERF_QUESTIONS}
                    and accuracy ≥ {pct(MIN_PERF_ACCURACY)}
                </p>
            </div>
            <div class="block">
                <p class="k">Data thresholds</p>
                <p>
                    A subtopic shows no performance status below {MIN_PERF_QUESTIONS}
                    graded questions. The calibrated cross-item model that predicts
                    <i>unseen</i>
                    questions is validated on a held-out item corpus plus a synthetic cohort,
                    and reads "not yet measured" on a real student until a real labelled dataset
                    exists, never a fabricated number.
                </p>
            </div>
        </div>
        <!-- Engine traceability, kept in source but not rendered in the UI:
        <p class="engine-src">
            Mirrors the per-subtopic performance gate in
            rslib/src/speedrun/mastery.rs · docs/score-models.md §2.
        </p>
        -->
    </div>

    <!-- ================= READINESS ================= -->
    <div
        id="panel-readiness"
        class="card readiness-card"
        role="tabpanel"
        aria-labelledby="tab-readiness"
        tabindex="0"
        hidden={active !== "readiness"}
    >
        <div class="card-head">
            <p class="metric-eyebrow">Signal 3 · Readiness</p>
            <h2>Would you pass today, and how sure are we?</h2>
            <!-- Named source, kept for traceability but not rendered in the UI:
            <p class="source-line">
                Source: the <b>P(pass) model</b> in the Rust engine
                (<code>compute_readiness</code>), from graded practice-test
                evidence.
            </p>
            -->
        </div>

        {#if score}
            <div class="live measured">
                <span class="badge">Score available</span>
                <p class="live-value">
                    {one(score.point)}
                    <span class="live-range">
                        ({one(score.low)}-{one(score.high)}) / {SCALE_MAX}
                    </span>
                </p>
                <p class="live-note">
                    P(pass today) {pct(score.passProbability)} · confidence {pct(
                        score.confidence,
                    )} · {pct(score.coveragePct)} coverage.
                </p>
            </div>
        {:else}
            <div class="live withheld">
                <span class="badge">
                    Withheld: {noScore ? "give-up rule" : "no data"}
                </span>
                <p class="live-value muted">Not enough data yet</p>
                {#if noScore}
                    <p class="live-note">{noScore.reason}</p>
                    <ul class="gates">
                        <li class:ok={reviewsMet}>
                            Graded reviews:
                            <b>{gradedReviews ?? "≥ 200"}</b>
                            / {MIN_GRADED_REVIEWS}
                        </li>
                        <li class:ok={coverageMet}>
                            Weighted coverage:
                            <b>{pct(coveragePct)}</b>
                            / {pct(MIN_COVERAGE)}
                        </li>
                        <li class:ok={practiceMet}>
                            Practice questions:
                            <b>{practiceQuestions}</b>
                            / {MIN_PRACTICE_QUESTIONS}
                        </li>
                    </ul>
                {/if}
            </div>
        {/if}

        <div class="explain">
            <div class="block">
                <p class="k">What data goes in</p>
                <p>
                    The proportion correct <b>p̂ = correct ÷ questions</b>
                    over all your graded practice-test questions, plus your weighted syllabus
                    coverage (each section weighted by its official SOA exam weight, so skipping
                    a heavy section can't read as "covered").
                </p>
            </div>
            <div class="block">
                <p class="k">How it is calculated</p>
                <p>
                    <b>Projected 0-{SCALE_MAX} band:</b>
                    the point is ≈ {SCALE_MAX}
                    × p̂; the range is {SCALE_MAX} × the
                    <b>95% Wilson interval</b>
                    on p̂ (robust for small samples), so it is always a range, never a bare
                    point.
                </p>
                <p>
                    <b>P(pass):</b>
                    SOA P passes at scaled ≥ {PASS_SCALED}, i.e. p̂ ≥ {PASS_PROPORTION} under
                    the linear map. Then
                    <span class="nowrap">
                        P(pass) = Φ((p̂ - {PASS_PROPORTION}) / se)
                    </span>
                    , <!-- dash-ok -->
                    with se = √(p̂(1−p̂)/n). The {PASS_PROPORTION} cutoff is a <!-- dash-ok -->
                    stated, recalibratable assumption, never tuned to flatter a result.
                </p>
                <p>
                    <b>Confidence</b>
                    rises with a tighter band and more coverage. Every score also carries
                    its reasons, the last-updated time, past-prediction accuracy (shown "not
                    yet available" until there is a track record), and the single best next
                    action: the honesty bundle, enforced by the type so a bare number can't
                    ship.
                </p>
                <p class="formula">
                    point = {SCALE_MAX}·p̂ · band = {SCALE_MAX}·Wilson₉₅(p̂) · P(pass) =
                    Φ((p̂ − {PASS_PROPORTION}) / se) <!-- dash-ok -->
                </p>
            </div>
            <div class="block">
                <p class="k">Data thresholds (give-up rule)</p>
                <p>
                    Below <b>
                        ≥ {MIN_GRADED_REVIEWS} graded reviews and ≥ {pct(MIN_COVERAGE)} weighted
                        coverage and ≥ {MIN_PRACTICE_QUESTIONS} graded practice questions
                    </b>
                    , the engine returns
                    <code>NoScore</code>
                    with the reason and the missing data. The projected band always comes
                    from your graded practice-test evidence and is always shown as a range.
                    <span class="method-note">
                        More representative tests count more: each test's evidence is
                        weighted by scope × source (a full official whole-exam test =
                        1.0; unit/subtopic drills and generated questions count less),
                        and the band uses that weighted proportion, while the give-up
                        rule above still counts your raw graded questions.
                    </span>
                </p>
            </div>
        </div>
        <!-- Engine traceability, kept in source but not rendered in the UI:
        <p class="engine-src">
            Mirrors <code>readiness_from_practice</code> /
            <code>wilson_interval</code> / <code>normal_cdf</code> in
            rslib/src/speedrun/service.rs · docs/score-models.md §3.
        </p>
        -->
    </div>
</div>

<style>
    .metrics {
        position: relative;
        z-index: 0;
        max-width: 940px;
        margin: 0 auto;
        padding: 2rem 1.5rem 4rem;
        color: var(--fg);
        font-family: var(--sr-font-body);
        font-size: var(--sr-text-base);
        line-height: 1.55;
    }

    /* Header: now just wraps the signal tabs. */
    .page-head {
        margin-bottom: 1.75rem;
    }
    /* Tab switcher: one signal's explanation at a time. Each tab carries its
       signal's accent (--tab-accent); the active tab reads as an accent-tinted
       pill with a clear accent ring, the same treatment as the home shell's
       view tabs, all from design tokens (no hardcoded colours). */
    .tabs {
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem;
        margin-top: 1.1rem;
    }
    .tab {
        border: 1px solid var(--border);
        background: var(--canvas-elevated);
        color: var(--fg);
        font-family: var(--sr-font-body);
        font-weight: 600;
        font-size: var(--sr-text-sm);
        padding: 0.4rem 0.9rem;
        border-radius: var(--sr-radius-pill);
        cursor: pointer;
        transition:
            border-color 0.2s ease,
            color 0.2s ease,
            background 0.2s ease;
    }
    .tab:hover {
        border-color: var(--tab-accent, var(--sr-accent));
        color: var(--tab-accent, var(--sr-accent));
        background: color-mix(
            in srgb,
            var(--tab-accent, var(--sr-accent)) 10%,
            transparent
        );
    }
    .tab.active {
        color: var(--tab-accent, var(--sr-accent));
        background: color-mix(
            in srgb,
            var(--tab-accent, var(--sr-accent)) 16%,
            transparent
        );
        border-color: color-mix(
            in srgb,
            var(--tab-accent, var(--sr-accent)) 55%,
            transparent
        );
        font-weight: 700;
    }
    .tab:focus-visible {
        outline: 2px solid var(--sr-focus);
        outline-offset: 2px;
    }

    /* Signal cards. Top-accent stripe colour-codes each section (decorative
       section identity only, per the design system). */
    .card {
        position: relative;
        border: 1px solid var(--border);
        border-radius: var(--sr-radius-lg);
        padding: 1.6rem 1.7rem;
        margin-bottom: 1.4rem;
        background: var(--canvas-elevated);
        box-shadow:
            inset 0 3px 0 0 var(--accent, var(--sr-accent)),
            var(--sr-shadow);
    }
    .card.memory {
        --accent: var(--sr-accent);
    }
    .card.performance {
        --accent: var(--sr-quaternary);
    }
    .card.readiness-card {
        --accent: var(--sr-quinary);
    }
    /* Only the active signal's panel shows; the others stay in the DOM (so each
       tab's aria-controls target stays valid) but are hidden. */
    .card[hidden] {
        display: none;
    }

    .card-head h2 {
        margin: 0.35rem 0 0;
        font-family: var(--sr-font-heading);
        font-size: 1.5rem;
        font-weight: 600;
        line-height: 1.1;
        letter-spacing: -0.01em;
    }
    .metric-eyebrow {
        margin: 0;
        font-family: var(--sr-font-body);
        font-size: var(--sr-text-xs);
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: var(--accent);
    }
    /* Live-inputs panel: measured (calm sage) vs withheld (honest amber). The
       state colour reads on the badge + a top accent (never a side stripe). */
    .live {
        margin: 1.1rem 0 0.4rem;
        padding: 1.1rem 1.2rem;
        border: 1px solid var(--border);
        border-radius: var(--sr-radius);
        background: var(--canvas-inset);
        box-shadow: inset 0 3px 0 0 var(--live-accent, var(--sr-pending));
    }
    .live.measured {
        --live-accent: var(--sr-mastered);
    }
    .live.withheld {
        --live-accent: var(--sr-progress);
    }
    .badge {
        display: inline-block;
        border: 1px solid var(--live-accent);
        color: var(--live-accent);
        font-family: var(--sr-font-body);
        font-weight: 700;
        font-size: var(--sr-text-xs);
        letter-spacing: 0.06em;
        text-transform: uppercase;
        border-radius: var(--sr-radius-pill);
        padding: 0.22rem 0.7rem;
    }
    .live-value {
        margin: 0.65rem 0 0;
        font-family: var(--sr-font-heading);
        font-size: 2rem;
        font-weight: 600;
        line-height: 1;
        color: var(--fg);
    }
    .live-value.muted {
        font-size: 1.35rem;
        color: var(--fg);
    }
    .live-range {
        font-family: var(--sr-font-body);
        font-size: 1rem;
        font-weight: 600;
        color: var(--fg-subtle);
    }
    .live-note {
        margin: 0.4rem 0 0;
        color: var(--fg-subtle);
        font-size: var(--sr-text-sm);
    }
    .gates {
        margin: 0.7rem 0 0;
        padding: 0;
        list-style: none;
        display: grid;
        gap: 0.35rem;
    }
    .gates li {
        font-size: var(--sr-text-sm);
        color: var(--fg-subtle);
    }
    .gates li::before {
        content: "○ ";
        color: var(--sr-progress);
        font-weight: 700;
    }
    .gates li.ok::before {
        content: "● ";
        color: var(--sr-mastered);
    }
    .gates li b {
        color: var(--fg);
    }

    /* Definitions grid */
    .explain {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
        gap: 1.1rem 1.5rem;
        margin-top: 1.1rem;
    }
    .block p {
        margin: 0.3rem 0 0;
        font-size: var(--sr-text-base);
    }
    .k {
        margin: 0;
        font-family: var(--sr-font-body);
        font-size: var(--sr-text-xs);
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: var(--fg-subtle);
    }
    .formula {
        margin-top: 0.6rem !important;
        padding: 0.55rem 0.7rem;
        background: var(--canvas-inset);
        border: 1px solid var(--border);
        border-radius: var(--sr-radius-sm);
        font-size: var(--sr-text-sm);
        letter-spacing: 0.01em;
        color: var(--fg);
    }
    .nowrap {
        white-space: nowrap;
    }
    .method-note {
        display: block;
        margin-top: 0.4rem;
        color: var(--fg-subtle);
        font-style: italic;
    }
    code {
        font-family: var(--sr-font-mono);
        font-size: 0.9em;
        background: var(--canvas-inset);
        padding: 0.05rem 0.3rem;
        border-radius: var(--sr-radius-sm);
    }
</style>
