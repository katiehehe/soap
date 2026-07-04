<!--
Copyright: Ankitects Pty Ltd and contributors
License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
-->
<script lang="ts">
    import { createEventDispatcher, onDestroy } from "svelte";

    import { bridgeCommand } from "@tslib/bridgecommand";

    import type { TestScope } from "../study-map/lib";
    import { subtopicTag, TAXONOMY } from "../study-map/lib";
    import { mathjax } from "./mathjax";

    // A timed, exam-shaped, ALL-multiple-choice practice test drawn from a
    // PRE-BUILT bank (the held-out corpus + the pre-generated templated /
    // verified-AI pool) — nothing is generated on the spot, so it starts
    // instantly and stays exactly timed. It comes in two shapes:
    //
    //   * FULL EXAM SIMULATION (the centre "Exam P" bubble / Practice tab):
    //     exactly 30 questions, section-weighted across the three units, on a
    //     visible 3:00:00 countdown. The canonical, most-representative test —
    //     it moves Readiness the most.
    //   * TOPIC / UNIT QUIZ (a subtopic or unit bubble): 10 questions at the same
    //     6-min-per-question exam pace (a 1:00:00 countdown). Records the same
    //     graded evidence, but counts LESS toward Readiness.
    //
    // Either way the countdown auto-submits at zero, and you can submit early at
    // any time. Grading is OBJECTIVE against the correct choice (no self-marking,
    // no peeking — the correct letter is withheld until submit and graded
    // server-side). It records REAL evidence for the Performance + Readiness
    // signals (readiness stays behind the give-up rule and is always a range).

    interface Choice {
        letter: string;
        text: string;
    }
    interface TestItem {
        id: string;
        stem: string;
        choices: Choice[];
        subtopic: string;
        unitId: string;
        difficulty: string;
        source: string;
        generated: boolean;
    }
    interface AssembleResult {
        items: TestItem[];
        corpus: { source: string; isRealSoa: boolean };
        seed: number;
    }
    interface ReviewRow {
        id: string;
        your: string;
        correct: boolean;
        correctLetter: string | null;
        answer: string;
        solution: string;
    }
    interface GradeResult {
        questions: number;
        correct: number;
        proportion: number;
        perUnit: Record<string, [number, number]>;
        stats: { questions: number; correct: number; tests: number };
        review: ReviewRow[];
    }

    type Phase = "intro" | "loading" | "testing" | "grading" | "results";

    // Scope of this test: one subtopic, a whole unit, or the whole exam. A unit
    // test interleaves that unit's subtopics; grading records per-subtopic
    // performance, so practicing a unit lifts every subtopic it touches. The
    // scope also picks the MODE (whole-exam => full simulation; otherwise a
    // scoped quiz) and sets how much the result counts toward Readiness.
    export let scope: TestScope = { kind: "all" };

    const dispatch = createEventDispatcher<{ done: void }>();
    const UNIT_NAME = new Map(TAXONOMY.map((u) => [u.id, u.name]));
    const SUB_NAME = new Map(
        TAXONOMY.flatMap((u) =>
            u.subtopics.map((s) => [subtopicTag(u.id, s.id), s.name] as const),
        ),
    );

    // The exam is 3 hours for 30 questions — i.e. 6 minutes (360s) per question.
    // A scoped quiz keeps that exam pace, so its clock scales with its length.
    const FULL_EXAM_SIZE = 30;
    const FULL_EXAM_SECONDS = 10_800; // 3:00:00
    const QUIZ_SIZE = 10;
    const SECONDS_PER_QUESTION = 360; // 6 min/question, the real exam's pace
    const LOW_TIME_SECONDS = 300; // colour the clock in the final 5 minutes

    // Whole-exam scope launches the full simulation; a unit/subtopic launches a
    // scoped quiz. Everything downstream (size, clock, readiness note) keys off
    // this one flag.
    $: isFullExam = scope.kind === "all";
    $: plannedSize = isFullExam ? FULL_EXAM_SIZE : QUIZ_SIZE;
    $: plannedSeconds = isFullExam
        ? FULL_EXAM_SECONDS
        : QUIZ_SIZE * SECONDS_PER_QUESTION;

    function scopeToStr(s: TestScope): string {
        if (s.kind === "unit") {
            return `unit:${s.id}`;
        }
        if (s.kind === "subtopic") {
            return `subtopic:${s.tag}`;
        }
        return "all";
    }
    function scopeToLabel(s: TestScope): string {
        if (s.kind === "unit") {
            return UNIT_NAME.get(s.id) ?? "this unit";
        }
        if (s.kind === "subtopic") {
            return SUB_NAME.get(s.tag) ?? "this topic";
        }
        return "the whole exam";
    }
    // How much a result of this scope counts toward Readiness — stated honestly
    // up front, mirroring the engine's representativeness weighting.
    function readinessNote(s: TestScope): string {
        if (s.kind === "subtopic") {
            return "A single-topic quiz counts the least toward your Readiness — take a full 30-question exam to move it the most.";
        }
        if (s.kind === "unit") {
            return "A unit quiz counts less toward your Readiness than a full, whole-exam simulation.";
        }
        return "A full, whole-exam simulation is the most representative test, so it moves your Readiness the most.";
    }
    $: scopeStr = scopeToStr(scope);
    $: scopeLabel = scopeToLabel(scope);
    $: readinessLine = readinessNote(scope);

    let phase: Phase = "intro";
    let items: TestItem[] = [];
    let corpus = { source: "", isRealSoa: false };
    // id -> the student's chosen letter (every question is multiple choice).
    // Never a self-marked right/wrong.
    let responses: Record<string, string> = {};
    let result: GradeResult | null = null;
    let reviewById: Record<string, ReviewRow> = {};

    // --- Countdown timer (part of Performance: the exam is timed) ------------
    let remaining = 0; // seconds left on the clock
    let timerId: ReturnType<typeof setInterval> | null = null;

    function stopTimer(): void {
        if (timerId !== null) {
            clearInterval(timerId);
            timerId = null;
        }
    }
    function startTimer(seconds: number): void {
        stopTimer();
        remaining = Math.max(0, Math.round(seconds));
        timerId = setInterval(() => {
            remaining -= 1;
            if (remaining <= 0) {
                remaining = 0;
                stopTimer();
                // Time's up: auto-submit whatever is answered (no confirm).
                submit(true);
            }
        }, 1000);
    }
    function fmtClock(s: number): string {
        const t = Math.max(0, Math.round(s));
        const hh = Math.floor(t / 3600);
        const mm = Math.floor((t % 3600) / 60);
        const ss = t % 60;
        const pad = (n: number) => String(n).padStart(2, "0");
        return `${pad(hh)}:${pad(mm)}:${pad(ss)}`;
    }
    $: lowTime = phase === "testing" && remaining <= LOW_TIME_SECONDS;

    function applyAssembled(d: AssembleResult): void {
        items = d?.items ?? [];
        corpus = d?.corpus ?? corpus;
        responses = {};
        result = null;
        reviewById = {};
        phase = items.length ? "testing" : "intro";
        if (phase === "testing") {
            // The full exam is a fixed 3:00:00; a scoped quiz keeps the same
            // 6-min-per-question pace over however many questions the bank could
            // supply for that scope.
            startTimer(
                isFullExam
                    ? FULL_EXAM_SECONDS
                    : items.length * SECONDS_PER_QUESTION,
            );
        }
    }
    onDestroy(stopTimer);

    $: total = items.length;
    $: answered = items.filter(
        (it) => (responses[it.id] ?? "").trim() !== "",
    ).length;
    $: allAnswered = total > 0 && answered === total;
    // Re-typeset MathJax when the phase (and thus the rendered container) changes.
    $: mjDep = `${phase}:${total}`;

    function startTest(): void {
        phase = "loading";
        // A fresh random seed each run gives a different exam-shaped draw every
        // time; the assembly itself stays reproducible for any given seed. Every
        // question comes from the PRE-BUILT bank — never generated on the spot.
        const seed = Math.floor(Math.random() * 1_000_000);
        bridgeCommand(
            `speedrun-assemble-test:${seed},${plannedSize},${scopeStr}`,
            applyAssembled,
        );
    }

    function choose(id: string, value: string): void {
        responses = { ...responses, [id]: value };
    }

    // `auto` is set only by the countdown hitting zero: it submits immediately
    // (no confirm). A manual early submit still warns about unanswered questions.
    function submit(auto = false): void {
        if (!auto && !allAnswered) {
            const missing = total - answered;
            const ok = confirm(
                `${missing} question${missing === 1 ? "" : "s"} still unanswered — ` +
                    "submit anyway? Unanswered questions are marked wrong.",
            );
            if (!ok) {
                return;
            }
        }
        stopTimer();
        phase = "grading";
        const payload = JSON.stringify({
            ids: items.map((i) => i.id),
            responses,
            scope: scopeStr,
            label: isFullExam ? "full exam simulation" : "topic practice quiz",
        });
        bridgeCommand(`speedrun-record-test:${payload}`, (r: GradeResult) => {
            result = r;
            reviewById = Object.fromEntries(
                (r?.review ?? []).map((x) => [x.id, x]),
            );
            phase = "results";
        });
    }

    function restart(): void {
        stopTimer();
        result = null;
        reviewById = {};
        responses = {};
        phase = "intro";
    }
    function backToMap(): void {
        stopTimer();
        dispatch("done");
    }

    function pct(x: number): string {
        return `${Math.round(x * 100)}%`;
    }
    // Conservative cleanup of the PDF-extracted text: collapse runaway
    // whitespace so stems and options read cleanly. (Deeper math fixes come from
    // re-authoring the items into LaTeX; MathJax then renders them.)
    function clean(s: string): string {
        return (s ?? "").replace(/\s+/g, " ").trim();
    }
</script>

<div class="ptest">
    {#if phase === "intro"}
        <section class="card intro">
            <h1>{isFullExam ? "Full exam simulation" : "Practice quiz"}</h1>
            <p class="scope-line">{scopeLabel}</p>
            <div class="specs">
                <div class="spec">
                    <span class="spec-num">{plannedSize}</span>
                    <span class="spec-label">questions</span>
                </div>
                <div class="spec">
                    <span class="spec-num">{fmtClock(plannedSeconds)}</span>
                    <span class="spec-label">
                        {isFullExam ? "on the clock" : "on the clock (exam pace)"}
                    </span>
                </div>
                <div class="spec">
                    <span class="spec-num">A–E</span>
                    <span class="spec-label">multiple choice</span>
                </div>
            </div>
            <p class="lead">
                {#if isFullExam}
                    An <b>exam-shaped</b>
                    test of exactly {FULL_EXAM_SIZE} multiple-choice questions, mixed
                    across the three units by the official SOA section weights (General
                    23–30% · Univariate 44–50% · Multivariate 23–30%) and timed like
                    the real exam.
                {:else}
                    An <b>exam-shaped</b>
                    quiz of {QUIZ_SIZE} multiple-choice questions on {scopeLabel}, at the
                    real exam's 6-minutes-per-question pace.
                {/if}
                Every question is drawn from a pre-built bank — nothing is generated
                while you test.
            </p>
            <p class="timing-line">
                A visible countdown <b>auto-submits at zero</b>; you can also submit
                early at any time.
            </p>
            <p class="note">
                Submitting records <b>real graded evidence</b>
                — each question is marked objectively against the correct choice (no
                self-marking). {readinessLine} It feeds Readiness, which stays hidden
                until the give-up threshold and always shows a range.
            </p>
            <div class="actions">
                <button class="btn primary" on:click={startTest}>
                    {isFullExam ? "Start exam" : "Start quiz"}
                </button>
                <button class="btn ghost" on:click={backToMap}>Back to map</button>
            </div>
        </section>
    {:else if phase === "loading"}
        <section class="card status">
            <p>Assembling your test…</p>
        </section>
    {:else if phase === "testing"}
        <div class="paper" use:mathjax={mjDep}>
            <div class="paper-head">
                <div class="paper-head-row">
                    <div>
                        <h1>{isFullExam ? "Full exam simulation" : "Practice quiz"}</h1>
                        <p class="scope-line">{scopeLabel} · {total} questions</p>
                    </div>
                    <div
                        class="clock"
                        class:low={lowTime}
                        role="timer"
                        aria-label="Time remaining"
                    >
                        <span class="clock-time">{fmtClock(remaining)}</span>
                        <span class="clock-label">remaining</span>
                    </div>
                </div>
                <p class="paper-hint">
                    Work each one and pick an answer. Nothing is marked until you
                    submit — the test auto-submits when the clock hits zero.
                </p>
            </div>

            {#each items as it, i}
                <section class="q">
                    <div class="q-head">
                        <span class="qnum">Question {i + 1}</span>
                        <!-- The unit is only worth labelling per-question on the
                             whole-exam test, where questions span the three units.
                             For a single-topic or single-unit test it's implied by
                             the header, so we drop the repetitive chip. -->
                        {#if scope.kind === "all"}
                            <span class="unit-chip">
                                {UNIT_NAME.get(it.unitId) ?? it.unitId}
                            </span>
                        {/if}
                    </div>
                    <div class="q-stem">{clean(it.stem)}</div>

                    <div
                        class="choices"
                        role="radiogroup"
                        aria-label="Answer choices for question {i + 1}"
                    >
                        {#each it.choices as c}
                            <label
                                class="choice"
                                class:selected={responses[it.id] === c.letter}
                            >
                                <input
                                    type="radio"
                                    name={"q-" + it.id}
                                    value={c.letter}
                                    checked={responses[it.id] === c.letter}
                                    on:change={() => choose(it.id, c.letter)}
                                />
                                <span class="choice-letter">{c.letter}</span>
                                <span class="choice-text">{clean(c.text)}</span>
                            </label>
                        {/each}
                    </div>
                </section>
            {/each}
        </div>

        <div class="submitbar">
            <span class="clock inline" class:low={lowTime} aria-hidden="true">
                <span class="clock-time">{fmtClock(remaining)}</span>
            </span>
            <span class="submit-count" class:done={allAnswered}>
                {answered} / {total} answered
            </span>
            <div class="actions">
                <button class="btn ghost" on:click={backToMap}>Back to map</button>
                <button class="btn primary" on:click={() => submit()}>
                    Submit test
                </button>
            </div>
        </div>
    {:else if phase === "grading"}
        <section class="card status"><p>Scoring your test…</p></section>
    {:else if phase === "results" && result}
        <div class="paper" use:mathjax={mjDep}>
            <section class="card results">
                <h1>Test complete</h1>
                <div class="score">
                    <span class="score-num">
                        {result.correct}
                        <span class="score-den">/{result.questions}</span>
                    </span>
                    <span class="score-pct">{pct(result.proportion)}</span>
                </div>
                <div class="breakdown">
                    <span class="bd-label">By section</span>
                    {#each Object.entries(result.perUnit) as [uid, cell]}
                        <div class="bd-row">
                            <span class="bd-unit">{UNIT_NAME.get(uid) ?? uid}</span>
                            <span class="bd-val">{cell[0]} / {cell[1]}</span>
                        </div>
                    {/each}
                </div>
                <p class="note">
                    Recorded as real evidence — <b>{result.stats.tests}</b>
                    {result.stats.tests === 1 ? "test" : "tests"} ·
                    <b>{result.stats.questions}</b>
                    questions graded all-time. Open the
                    <b>Readiness</b>
                    tab to see how this moves your P(pass) band; it stays hidden until
                    you have enough evidence, and is always a range.
                </p>
                <div class="actions">
                    <button class="btn primary" on:click={restart}>
                        Take another test
                    </button>
                    <button class="btn ghost" on:click={backToMap}>
                        Back to map
                    </button>
                </div>
            </section>

            <h2 class="review-title">Review — every question</h2>
            {#each items as it, i}
                {@const r = reviewById[it.id]}
                <section
                    class="q review"
                    class:correct={r?.correct}
                    class:wrong={r && !r.correct}
                >
                    <div class="q-head">
                        <span class="qnum">Question {i + 1}</span>
                        <span class="verdict {r?.correct ? 'ok' : 'bad'}">
                            {r?.correct ? "Correct" : "Incorrect"}
                        </span>
                    </div>
                    <div class="q-stem">{clean(it.stem)}</div>

                    <div class="choices">
                        {#each it.choices as c}
                            <div
                                class="choice ro"
                                class:correct-choice={r?.correctLetter === c.letter}
                                class:your-wrong={r &&
                                    !r.correct &&
                                    r.your === c.letter}
                            >
                                <span class="choice-letter">{c.letter}</span>
                                <span class="choice-text">{clean(c.text)}</span>
                                {#if r?.correctLetter === c.letter}
                                    <span class="pill ok">correct</span>
                                {:else if r && !r.correct && r.your === c.letter}
                                    <span class="pill bad">your answer</span>
                                {/if}
                            </div>
                        {/each}
                    </div>

                    {#if r?.solution}
                        <div class="answer">
                            <span class="answer-label">Worked solution</span>
                            <div class="answer-body">{clean(r.solution)}</div>
                        </div>
                    {/if}
                </section>
            {/each}
        </div>
    {/if}
</div>

<style>
    .ptest {
        max-width: 780px;
        margin: 0 auto;
        padding: 2rem 1.5rem 3rem;
        font-family: var(--sr-font-body);
        color: var(--fg);
    }
    .card {
        background: var(--canvas-elevated);
        border: 1px solid var(--border);
        border-radius: var(--sr-radius, 16px);
        box-shadow: var(--sr-shadow-sm);
        padding: 1.75rem;
    }
    h1 {
        font-family: var(--sr-font-heading);
        font-weight: 800;
        font-size: 1.55rem;
        letter-spacing: -0.01em;
        margin: 0 0 0.25rem;
    }
    .scope-line {
        margin: 0 0 0.9rem;
        font-size: 0.8rem;
        font-weight: 800;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: var(--sr-accent);
    }
    .lead {
        font-size: 1rem;
        line-height: 1.6;
        margin: 0 0 0.9rem;
    }
    .note {
        font-size: 0.9rem;
        line-height: 1.55;
        color: var(--fg-subtle);
        background: var(--sr-accent-weak);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 0.7rem 0.9rem;
        margin: 0 0 1.1rem;
    }
    .timing-line {
        font-size: 0.9rem;
        line-height: 1.55;
        color: var(--fg-subtle);
        margin: 0 0 1.1rem;
    }

    /* Intro specs strip: the fixed shape of this mode (count · clock · format) */
    .specs {
        display: flex;
        gap: 0.6rem;
        flex-wrap: wrap;
        margin: 0 0 1.2rem;
    }
    .spec {
        flex: 1 1 0;
        min-width: 8rem;
        display: flex;
        flex-direction: column;
        gap: 0.15rem;
        padding: 0.8rem 1rem;
        border: 1px solid var(--border);
        border-radius: var(--sr-radius-sm, 10px);
        background: var(--canvas);
    }
    .spec-num {
        font-family: var(--sr-font-body);
        font-weight: 800;
        font-size: 1.35rem;
        line-height: 1.1;
        font-variant-numeric: tabular-nums;
        color: var(--fg);
    }
    .spec-label {
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: var(--fg-subtle);
    }

    /* Countdown clock (testing phase) */
    .clock {
        display: flex;
        flex-direction: column;
        align-items: flex-end;
        gap: 0.1rem;
        padding: 0.45rem 0.8rem;
        border: 1px solid var(--border);
        border-radius: var(--sr-radius-sm, 10px);
        background: var(--canvas);
    }
    .clock-time {
        font-family: var(--sr-font-body);
        font-weight: 800;
        font-size: 1.5rem;
        line-height: 1;
        font-variant-numeric: tabular-nums;
        color: var(--fg);
    }
    .clock-label {
        font-size: 0.65rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: var(--fg-subtle);
    }
    /* Honest urgency in the final minutes — a colour shift, never a glow. */
    .clock.low {
        border-color: color-mix(in srgb, #c0392b 55%, var(--border));
    }
    .clock.low .clock-time {
        color: #c0392b;
    }
    .clock.inline {
        flex-direction: row;
        align-items: baseline;
        padding: 0.2rem 0.6rem;
    }
    .clock.inline .clock-time {
        font-size: 1.15rem;
    }

    .actions {
        display: flex;
        gap: 0.6rem;
        flex-wrap: wrap;
        margin-top: 0.4rem;
    }
    .btn {
        font-family: var(--sr-font-body);
        font-weight: 700;
        font-size: 0.95rem;
        padding: 0.65rem 1.3rem;
        border-radius: var(--sr-radius-sm, 10px);
        border: 1px solid transparent;
        cursor: pointer;
        transition:
            transform 0.1s ease,
            filter 0.15s ease,
            background 0.15s ease;
    }
    .btn:active {
        transform: translateY(1px);
    }
    .btn.primary {
        background: var(--sr-accent);
        color: #fbfaf6;
        box-shadow: var(--sr-shadow-sm);
    }
    .btn.primary:hover {
        filter: brightness(1.06);
    }
    .btn.ghost {
        background: transparent;
        border-color: var(--border);
        color: var(--fg);
    }
    .btn.ghost:hover {
        border-color: var(--sr-accent);
        color: var(--sr-accent);
    }

    .status p {
        margin: 0;
        font-size: 1rem;
        color: var(--fg-subtle);
        text-align: center;
    }

    /* One-page test "paper" */
    .paper {
        display: flex;
        flex-direction: column;
        gap: 1rem;
    }
    .paper-head {
        margin-bottom: 0.2rem;
    }
    .paper-head-row {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 1rem;
        flex-wrap: wrap;
    }
    .paper-hint {
        margin: 0.5rem 0 0;
        font-size: 0.88rem;
        color: var(--fg-subtle);
    }

    /* A single question card */
    .q {
        background: var(--canvas-elevated);
        border: 1px solid var(--border);
        border-radius: var(--sr-radius, 14px);
        box-shadow: var(--sr-shadow-sm);
        padding: 1.2rem 1.3rem 1.3rem;
    }
    .q-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.75rem;
        margin-bottom: 0.6rem;
    }
    .qnum {
        font-weight: 700;
        font-size: 0.78rem;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        color: var(--fg-subtle);
    }
    .unit-chip {
        font-size: 0.75rem;
        font-weight: 700;
        padding: 0.22rem 0.65rem;
        border-radius: var(--sr-radius-pill, 999px);
        background: var(--sr-accent-weak);
        color: var(--sr-accent);
        border: 1px solid var(--border);
    }
    .q-stem {
        font-size: 1.05rem;
        line-height: 1.6;
        margin-bottom: 1rem;
    }

    /* Choices */
    .choices {
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
    }
    .choice {
        display: flex;
        align-items: baseline;
        gap: 0.7rem;
        padding: 0.6rem 0.8rem;
        border: 1px solid var(--border);
        border-radius: var(--sr-radius-sm, 10px);
        background: var(--canvas);
        cursor: pointer;
        transition:
            border-color 0.15s ease,
            background 0.15s ease;
    }
    .choice:hover {
        border-color: var(--sr-accent);
    }
    .choice.selected {
        border-color: var(--sr-accent);
        background: var(--sr-accent-weak);
    }
    .choice input {
        margin: 0;
        accent-color: var(--sr-accent);
    }
    .choice-letter {
        font-weight: 800;
        min-width: 1.1em;
        color: var(--fg);
    }
    .choice-text {
        line-height: 1.5;
    }
    .choice.ro {
        cursor: default;
    }
    .choice.ro:hover {
        border-color: var(--border);
    }

    /* Sticky submit bar */
    .submitbar {
        position: sticky;
        bottom: 0;
        margin-top: 1rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        flex-wrap: wrap;
        padding: 0.8rem 1rem;
        background: var(--canvas-elevated);
        border: 1px solid var(--border);
        border-radius: var(--sr-radius, 14px);
        box-shadow: var(--sr-shadow);
    }
    .submit-count {
        font-weight: 700;
        font-size: 0.9rem;
        color: var(--fg-subtle);
    }
    .submit-count.done {
        color: var(--sr-secondary);
    }

    /* Results */
    .score {
        display: flex;
        align-items: baseline;
        gap: 1rem;
        margin: 0.5rem 0 1.3rem;
    }
    .score-num {
        font-family: var(--sr-font-heading);
        font-weight: 800;
        font-size: 3rem;
        line-height: 1;
        color: var(--sr-accent);
    }
    .score-den {
        font-size: 1.4rem;
        color: var(--fg-subtle);
    }
    .score-pct {
        font-size: 1.4rem;
        font-weight: 700;
        color: var(--fg-subtle);
    }
    .breakdown {
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 0.9rem 1rem;
        margin-bottom: 1.1rem;
    }
    .bd-label {
        display: block;
        font-size: 0.72rem;
        font-weight: 800;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: var(--fg-subtle);
        margin-bottom: 0.5rem;
    }
    .bd-row {
        display: flex;
        justify-content: space-between;
        padding: 0.3rem 0;
        border-top: 1px solid var(--border);
        font-size: 0.95rem;
    }
    .bd-row:first-of-type {
        border-top: none;
    }
    .bd-unit {
        color: var(--fg);
    }
    .bd-val {
        font-weight: 700;
    }

    /* Review */
    .review-title {
        margin: 0.4rem 0 0;
        font-family: var(--sr-font-heading);
        font-weight: 700;
        font-size: 1.15rem;
    }
    .q.review.correct {
        border-color: color-mix(in srgb, #2f855a 45%, var(--border));
    }
    .q.review.wrong {
        border-color: color-mix(in srgb, #c0392b 45%, var(--border));
    }
    .verdict {
        font-size: 0.72rem;
        font-weight: 800;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        padding: 0.22rem 0.65rem;
        border-radius: var(--sr-radius-pill, 999px);
    }
    .verdict.ok {
        background: color-mix(in srgb, #2f855a 18%, transparent);
        color: #2f855a;
    }
    .verdict.bad {
        background: color-mix(in srgb, #c0392b 16%, transparent);
        color: #c0392b;
    }
    .choice.correct-choice {
        border-color: #2f855a;
        background: color-mix(in srgb, #2f855a 12%, var(--canvas));
    }
    .choice.your-wrong {
        border-color: #c0392b;
        background: color-mix(in srgb, #c0392b 10%, var(--canvas));
    }
    .pill {
        margin-left: auto;
        font-size: 0.68rem;
        font-weight: 800;
        letter-spacing: 0.03em;
        text-transform: uppercase;
        padding: 0.15rem 0.5rem;
        border-radius: var(--sr-radius-pill, 999px);
    }
    .pill.ok {
        background: #2f855a;
        color: #fbfaf6;
    }
    .pill.bad {
        background: #c0392b;
        color: #fbfaf6;
    }
    .answer {
        margin-top: 0.9rem;
        background: var(--canvas);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 0.9rem 1rem;
    }
    .answer-label {
        display: block;
        font-size: 0.72rem;
        font-weight: 800;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: var(--sr-accent);
        margin-bottom: 0.35rem;
    }
    .answer-body {
        font-size: 1rem;
        line-height: 1.6;
    }
</style>
