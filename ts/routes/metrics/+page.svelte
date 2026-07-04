<!--
Copyright: Ankitects Pty Ltd and contributors
License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
-->
<script lang="ts">
    import { onMount } from "svelte";

    import { computeReadiness, getMasteryState } from "@generated/backend";
    import type {
        MasteryState,
        ReadinessResult,
    } from "@generated/anki/speedrun_pb";

    // Reuse the SAME taxonomy + weights the map/readiness screens send, so the
    // live inputs shown here match the numbers the engine computes elsewhere.
    import { masteryInputs } from "../study-map/lib";
    import {
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

    // When embedded in the Home shell, the parent passes the signal to reveal
    // (e.g. after a click on a readiness card). As a standalone route we read the
    // URL hash instead (/metrics#memory). Either way we scroll to it and flash it.
    export let anchor: MetricId | null = null;

    let readiness: ReadinessResult | null = null;
    let mastery: MasteryState | null = null;
    let mounted = false;
    let flashId: MetricId | null = null;

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

    function scrollToMetric(id: MetricId | null): void {
        if (!id || !mounted || typeof document === "undefined") {
            return;
        }
        requestAnimationFrame(() => {
            const el = document.getElementById(id);
            if (!el) {
                return;
            }
            el.scrollIntoView({ behavior: "smooth", block: "start" });
            flashId = id;
            window.setTimeout(() => {
                if (flashId === id) {
                    flashId = null;
                }
            }, 1500);
        });
    }

    onMount(async () => {
        mounted = true;
        const hash =
            typeof window !== "undefined"
                ? (window.location.hash.replace("#", "") as MetricId)
                : null;
        const target = anchor ?? (hash || null);
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
            // Live inputs are a bonus — the definitions render without the engine.
        }
        scrollToMetric(target);
    });

    // React to a parent-driven anchor change while already mounted.
    $: if (mounted && anchor) {
        scrollToMetric(anchor);
    }
</script>

<div class="metrics">
    <header class="page-head">
        <p class="eyebrow">How the metrics work</p>
        <h1>Three signals, never blended</h1>
        <p class="subtitle">
            Every number in this app answers one specific question, comes from a
            named source, and is shown with its uncertainty. This page is the
            whole method, in the open: what each signal means, exactly what data
            feeds it, and how it is computed. Where the engine has your data, you
            will see your own live inputs; where it does not, the signal
            <b>abstains</b> — an honest amber "not yet", never a guess in a nice
            font.
        </p>
        <nav class="jump" aria-label="Jump to a signal">
            <button type="button" on:click={() => scrollToMetric("memory")}>
                Memory
            </button>
            <button type="button" on:click={() => scrollToMetric("performance")}>
                Performance
            </button>
            <button type="button" on:click={() => scrollToMetric("readiness")}>
                Readiness
            </button>
        </nav>
    </header>

    <!-- The shared give-up rule, stated up front. It is a Rust assertion, not a
         UI hint: below threshold the readiness type literally cannot hold a
         number. -->
    <section class="rule">
        <p class="k">The give-up rule (enforced in Rust)</p>
        <p>
            Readiness stays <b>withheld</b> until there are
            <b>≥ {MIN_GRADED_REVIEWS} graded reviews</b>
            <b>and</b>
            <b>≥ {pct(MIN_COVERAGE)} weighted syllabus coverage</b>
            <b>and</b>
            <b>≥ {MIN_PRACTICE_QUESTIONS} graded practice-test questions</b>. Below
            any of these, <code>compute_readiness</code> returns
            <code>NoScore</code> with the reason and what is missing — a bare
            readiness number cannot be emitted, because the return type is a
            <code>oneof</code>. Memory and Performance abstain on their own data,
            independently of this gate.
        </p>
        <p class="src">Source: rslib/src/speedrun/service.rs · docs/score-models.md</p>
    </section>

    <!-- ================= MEMORY ================= -->
    <section id="memory" class="card memory" class:flash={flashId === "memory"}>
        <div class="card-head">
            <p class="metric-eyebrow">Signal 1 · Memory</p>
            <h2>Can you recall this fact right now?</h2>
            <p class="source-line">
                Source: <b>FSRS retrievability</b> — Anki's spaced-repetition
                model, in the shared Rust engine.
            </p>
        </div>

        <div class="live {memory?.hasData ? 'measured' : 'withheld'}">
            <span class="badge">{memory?.hasData ? "Measured" : "Withheld — no reviews yet"}</span>
            {#if memory?.hasData}
                <p class="live-value">
                    {pct(memory.point)}
                    <span class="live-range">
                        ({pct(memory.low)}–{pct(memory.high)})
                    </span>
                </p>
                <p class="live-note">
                    Mean P(recall today) across {memory.reviewedCards} reviewed
                    cards · range is the 10th–90th percentile.
                </p>
            {:else}
                <p class="live-value muted">Not yet scored</p>
                <p class="live-note">
                    No syllabus card has a graded review, so Memory shows nothing
                    rather than a fabricated number.
                </p>
            {/if}
        </div>

        <div class="explain">
            <div class="block">
                <p class="k">What data goes in</p>
                <p>
                    Your review history, per card — the grades and timing FSRS
                    uses to fit each card's forgetting curve. Only cards tagged to
                    the syllabus that you have actually reviewed count.
                </p>
            </div>
            <div class="block">
                <p class="k">How it is calculated</p>
                <p>
                    For every reviewed syllabus card the engine reads FSRS's
                    predicted probability of recall <i>today</i>. The point value
                    is the <b>mean</b> of those per-card probabilities; the range
                    is their <b>10th–90th percentile</b>, so you see the spread,
                    not just an average. It never mixes in practice-test results.
                </p>
                <p class="formula">
                    point = mean(P(recall)) · band = [P10, P90] over reviewed
                    cards
                </p>
            </div>
            <div class="block">
                <p class="k">Data thresholds</p>
                <p>
                    Abstains until at least one syllabus card has a graded review
                    (<code>has_data = false</code> when empty). No reviews → no
                    number, by construction.
                </p>
            </div>
        </div>
        <p class="engine-src">
            Mirrors <code>memory_recall</code> in rslib/src/speedrun/mastery.rs,
            surfaced by <code>compute_readiness</code>.
        </p>
    </section>

    <!-- ================= PERFORMANCE ================= -->
    <section
        id="performance"
        class="card performance"
        class:flash={flashId === "performance"}
    >
        <div class="card-head">
            <p class="metric-eyebrow">Signal 2 · Performance</p>
            <h2>Can you solve a new, exam-style question?</h2>
            <p class="source-line">
                Source: <b>graded multiple-choice practice tests</b> — procedure,
                not recall.
            </p>
        </div>

        <div class="live {perf.withData > 0 ? 'measured' : 'withheld'}">
            <span class="badge">
                {perf.withData > 0
                    ? "Measured (per subtopic)"
                    : "Withheld — no graded questions yet"}
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
                    )}). Shown as measured counts, never as one blended score.
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
                    Correct / total on <b>disguised, parameterized</b> A–E
                    questions, tallied <b>per subtopic</b>. The numbers regenerate
                    on each attempt, so this measures whether you can run the
                    procedure — not whether you recognise a memorised cue.
                </p>
            </div>
            <div class="block">
                <p class="k">How it is calculated</p>
                <p>
                    Per subtopic, performance accuracy = correct ÷ graded
                    questions. A subtopic reads <b>mastered</b> once it has ≥ {MIN_PERF_QUESTIONS}
                    graded questions <b>and</b> ≥ {pct(MIN_PERF_ACCURACY)} correct
                    ("strong"). Performance is kept <b>separate</b> from Memory:
                    it can satisfy a prerequisite in the guided map, but it never
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
                    <i>unseen</i> questions is validated on a held-out item corpus
                    plus a synthetic cohort, and reads "not yet measured" on a real
                    student until a real labelled dataset exists — never a
                    fabricated number.
                </p>
            </div>
        </div>
        <p class="engine-src">
            Mirrors the per-subtopic performance gate in
            rslib/src/speedrun/mastery.rs · docs/score-models.md §2.
        </p>
    </section>

    <!-- ================= READINESS ================= -->
    <section
        id="readiness"
        class="card readiness-card"
        class:flash={flashId === "readiness"}
    >
        <div class="card-head">
            <p class="metric-eyebrow">Signal 3 · Readiness</p>
            <h2>Would you pass today, and how sure are we?</h2>
            <p class="source-line">
                Source: the <b>P(pass) model</b> in the Rust engine
                (<code>compute_readiness</code>), from graded practice-test
                evidence.
            </p>
        </div>

        {#if score}
            <div class="live measured">
                <span class="badge">Score available</span>
                <p class="live-value">
                    {one(score.point)}
                    <span class="live-range">
                        ({one(score.low)}–{one(score.high)}) / {SCALE_MAX}
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
                <span class="badge">Withheld — {noScore ? "give-up rule" : "no data"}</span>
                <p class="live-value muted">Not enough data yet</p>
                {#if noScore}
                    <p class="live-note">{noScore.reason}</p>
                    <ul class="gates">
                        <li class:ok={reviewsMet}>
                            Graded reviews:
                            <b>{gradedReviews ?? "≥ 200"}</b> / {MIN_GRADED_REVIEWS}
                        </li>
                        <li class:ok={coverageMet}>
                            Weighted coverage:
                            <b>{pct(coveragePct)}</b> / {pct(MIN_COVERAGE)}
                        </li>
                        <li class:ok={practiceMet}>
                            Practice questions:
                            <b>{practiceQuestions}</b> / {MIN_PRACTICE_QUESTIONS}
                        </li>
                    </ul>
                {/if}
            </div>
        {/if}

        <div class="explain">
            <div class="block">
                <p class="k">What data goes in</p>
                <p>
                    The proportion correct <b>p̂ = correct ÷ questions</b> over all
                    your graded practice-test questions, plus your weighted
                    syllabus coverage (each section weighted by its official SOA
                    exam weight, so skipping a heavy section can't read as
                    "covered").
                </p>
            </div>
            <div class="block">
                <p class="k">How it is calculated</p>
                <p>
                    <b>Projected 0–{SCALE_MAX} band:</b> the point is ≈ {SCALE_MAX}
                    × p̂; the range is {SCALE_MAX} × the <b>95% Wilson interval</b>
                    on p̂ (robust for small samples), so it is always a range, never
                    a bare point.
                </p>
                <p>
                    <b>P(pass):</b> SOA P passes at scaled ≥ {PASS_SCALED}, i.e.
                    p̂ ≥ {PASS_PROPORTION} under the linear map. Then
                    <span class="nowrap">P(pass) = Φ((p̂ − {PASS_PROPORTION}) / se)</span>,
                    with se = √(p̂(1−p̂)/n). The {PASS_PROPORTION} cutoff is a
                    stated, recalibratable assumption — never tuned to flatter a
                    result.
                </p>
                <p>
                    <b>Confidence</b> rises with a tighter band and more coverage.
                    Every score also carries its reasons, the last-updated time,
                    past-prediction accuracy (shown "not yet available" until
                    there is a track record), and the single best next action —
                    the honesty bundle, enforced by the type so a bare number
                    can't ship.
                </p>
                <p class="formula">
                    point = {SCALE_MAX}·p̂ · band = {SCALE_MAX}·Wilson₉₅(p̂) ·
                    P(pass) = Φ((p̂ − {PASS_PROPORTION}) / se)
                </p>
            </div>
            <div class="block">
                <p class="k">Data thresholds (give-up rule)</p>
                <p>
                    Below <b>≥ {MIN_GRADED_REVIEWS} graded reviews and ≥ {pct(
                        MIN_COVERAGE,
                    )} weighted coverage and ≥ {MIN_PRACTICE_QUESTIONS} graded
                    practice questions</b>, the engine returns
                    <code>NoScore</code> with the reason and the missing data. The
                    projected band always comes from your graded practice-test
                    evidence and is always shown as a range.
                    <span class="method-note">
                        More representative tests count more: each test's evidence is
                        weighted by scope × source (a full official whole-exam test =
                        1.0; unit/subtopic drills and generated questions count less),
                        and the band uses that weighted proportion — while the give-up
                        rule above still counts your raw graded questions.
                    </span>
                </p>
            </div>
        </div>
        <p class="engine-src">
            Mirrors <code>readiness_from_practice</code> /
            <code>wilson_interval</code> / <code>normal_cdf</code> in
            rslib/src/speedrun/service.rs · docs/score-models.md §3.
        </p>
    </section>
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
        font-size: 15px;
        line-height: 1.55;
    }

    /* Header */
    .page-head {
        margin-bottom: 1.75rem;
    }
    .eyebrow {
        margin: 0;
        font-family: var(--sr-font-body);
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        color: var(--sr-accent);
    }
    .page-head h1 {
        margin: 0.5rem 0 0;
        font-family: var(--sr-font-heading);
        font-size: clamp(2rem, 4.5vw, 2.9rem);
        font-weight: 600;
        line-height: 1.05;
        letter-spacing: -0.01em;
    }
    .subtitle {
        margin: 0.7rem 0 0;
        max-width: 68ch;
        color: var(--fg-subtle);
        font-size: 0.95rem;
    }
    .jump {
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem;
        margin-top: 1.1rem;
    }
    .jump button {
        border: 1px solid var(--border);
        background: var(--canvas-elevated);
        color: var(--fg);
        font-family: var(--sr-font-body);
        font-weight: 600;
        font-size: 0.8rem;
        padding: 0.4rem 0.9rem;
        border-radius: var(--sr-radius-pill);
        cursor: pointer;
        transition:
            border-color 0.2s ease,
            color 0.2s ease,
            background 0.2s ease;
    }
    .jump button:hover {
        border-color: var(--sr-accent);
        color: var(--sr-accent);
        background: var(--sr-accent-weak);
    }
    .jump button:focus-visible {
        outline: 2px solid var(--sr-focus);
        outline-offset: 2px;
    }

    /* Give-up rule callout — honest amber top accent (we're withholding). */
    .rule {
        border: 1px solid var(--border);
        border-top: 3px solid var(--sr-progress);
        border-radius: var(--sr-radius-lg);
        padding: 1.3rem 1.5rem;
        margin-bottom: 1.6rem;
        background: var(--canvas-elevated);
        box-shadow: var(--sr-shadow-sm);
    }
    .rule p {
        margin: 0.5rem 0 0;
    }
    .rule p:first-child {
        margin-top: 0;
    }

    /* Signal cards. Top-accent stripe colour-codes each section (decorative
       section identity only, per the design system). */
    .card {
        position: relative;
        border: 1px solid var(--border);
        border-top: 3px solid var(--accent, var(--sr-accent));
        border-radius: var(--sr-radius-lg);
        padding: 1.6rem 1.7rem;
        margin-bottom: 1.4rem;
        background: var(--canvas-elevated);
        box-shadow: var(--sr-shadow);
        scroll-margin-top: 1rem;
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
    /* Brief, calm highlight when navigated to (no glow). */
    .card.flash {
        animation: metric-flash 1.5s ease;
    }
    @keyframes metric-flash {
        0%,
        100% {
            box-shadow: var(--sr-shadow);
        }
        30% {
            box-shadow:
                var(--sr-shadow),
                inset 0 0 0 2px var(--accent);
        }
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
        font-size: 0.68rem;
        font-weight: 700;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: var(--accent);
    }
    .source-line {
        margin: 0.6rem 0 0;
        color: var(--fg-subtle);
        font-size: 0.9rem;
    }

    /* Live-inputs panel — measured (calm sage) vs withheld (honest amber). */
    .live {
        margin: 1.1rem 0 0.4rem;
        padding: 1.1rem 1.2rem;
        border: 1px solid var(--border);
        border-left: 3px solid var(--live-accent, var(--sr-pending));
        border-radius: var(--sr-radius);
        background: var(--canvas-inset);
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
        font-size: 0.66rem;
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
        font-size: 0.85rem;
    }
    .gates {
        margin: 0.7rem 0 0;
        padding: 0;
        list-style: none;
        display: grid;
        gap: 0.35rem;
    }
    .gates li {
        font-size: 0.85rem;
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
        font-size: 0.9rem;
    }
    .k {
        margin: 0;
        font-family: var(--sr-font-body);
        font-size: 0.7rem;
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
        font-size: 0.82rem;
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
    .engine-src,
    .rule .src {
        margin: 1rem 0 0;
        font-family: var(--sr-font-body);
        font-size: 0.72rem;
        color: var(--fg-subtle);
    }
    code {
        font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
        font-size: 0.85em;
        background: var(--canvas-inset);
        padding: 0.05rem 0.3rem;
        border-radius: 4px;
    }
</style>
