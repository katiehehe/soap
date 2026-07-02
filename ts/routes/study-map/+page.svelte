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
        SubtopicMastery,
    } from "@generated/anki/speedrun_pb";

    import type { LeafNode, SubtopicEvidence } from "./lib";
    import {
        COLORS,
        computeLayout,
        edgeBetween,
        hasEnoughEvidence,
        leafProgress,
        MIN_PROBLEMS,
        statusLabel,
    } from "./lib";

    const layout = computeLayout();
    const { center, units } = layout;
    const allTags = units.flatMap((u) => u.subs.map((s) => s.tag));

    // Official SOA P section weights (range midpoints), matching the readiness
    // dashboard so the give-up rule evaluates identical coverage here.
    const UNIT_WEIGHTS = [
        { unitId: "general", weight: 26.5 },
        { unitId: "univariate", weight: 47 },
        { unitId: "multivariate", weight: 26.5 },
    ];

    const GREY = COLORS.grey;
    const AMBER = COLORS.amber;
    const GREEN = COLORS.green;
    const ACCENT = COLORS.accent;

    let result: MasteryState | null = null;
    let readiness: ReadinessResult | null = null;
    let loadError = "";
    let selected: LeafNode | null = null;

    // Scale the fixed-size diagram to fit the available width (never upscaling),
    // keeping labels readable. A uniform scale preserves the (verified)
    // non-overlapping geometry; the page scrolls if the map is taller than the
    // dialog.
    let viewportWidth = 0;
    $: scale = viewportWidth > 0 ? Math.min(1, viewportWidth / layout.width) : 1;

    onMount(async () => {
        try {
            [result, readiness] = await Promise.all([
                getMasteryState({ expectedSubtopics: allTags }),
                computeReadiness({ expectedSubtopics: allTags, units: UNIT_WEIGHTS }),
            ]);
        } catch (err) {
            loadError = String(err);
        }
    });

    $: subMap = new Map<string, SubtopicMastery>(
        (result?.subtopics ?? []).map((s) => [s.tag, s]),
    );
    $: unitMap = new Map((result?.units ?? []).map((u) => [u.unitId, u]));
    $: overall = result?.overall ?? null;

    // Honest readiness give-up state — never a fabricated number. The score
    // itself lives on the Readiness page; here we only surface why it's withheld.
    $: noScore = readiness?.value.case === "noScore" ? readiness.value.value : null;

    /** The subtopic's measured evidence, or null if we have none for it. */
    function ev(tag: string): SubtopicEvidence | null {
        return subMap.get(tag) ?? null;
    }

    function leafCleared(tag: string): boolean {
        return subMap.get(tag)?.gateCleared ?? false;
    }

    function unitProgress(id: string): number {
        const u = unitMap.get(id);
        if (!u || u.subtopicsTotal === 0) {
            return 0;
        }
        return u.subtopicsCleared / u.subtopicsTotal;
    }

    function colorFor(progress: number, cleared: boolean): string {
        if (cleared || progress >= 1) {
            return GREEN;
        }
        if (progress > 0) {
            return AMBER;
        }
        return GREY;
    }

    interface Edge {
        x1: number;
        y1: number;
        x2: number;
        y2: number;
        progress: number;
        color: string;
    }

    $: edges = [
        ...units.map((u): Edge => {
            const g = edgeBetween(center, u);
            const p = unitProgress(u.id);
            return {
                ...g,
                progress: p,
                color: colorFor(p, unitMap.get(u.id)?.mastered ?? false),
            };
        }),
        ...units.flatMap((u) =>
            u.subs.map((s): Edge => {
                const g = edgeBetween(u, s);
                const p = leafProgress(ev(s.tag));
                return { ...g, progress: p, color: colorFor(p, leafCleared(s.tag)) };
            }),
        ),
    ];

    function pct(x: number): string {
        return `${Math.round(x * 100)}%`;
    }

    function segWidth(n: number): string {
        const total = overall?.subtopicsTotal ?? 0;
        return total > 0 ? `${(n / total) * 100}%` : "0%";
    }

    function select(node: LeafNode): void {
        selected = node;
    }
</script>

<div class="study-map">
    <header>
        <h1>Study map</h1>
        <p class="exam">SOA Exam P · Probability</p>
        <p class="subtitle">
            Tap a subtopic to see its mastery. Each link fills as you clear its gate:
            <span class="key" style="color:{GREY}">■</span>
            not started,
            <span class="key" style="color:{AMBER}">■</span>
            gathering data / in progress,
            <span class="key" style="color:{GREEN}">■</span>
            mastered. Mastery is measured from real reviews, never guessed.
        </p>
    </header>

    {#if loadError}
        <div class="notice error">Couldn't load mastery: {loadError}</div>
    {/if}

    {#if overall}
        <section class="overall" aria-label="Overall mastery">
            <div class="overall-head">
                <h2>Overall mastery</h2>
                <span class="overall-count">
                    {overall.subtopicsMastered} / {overall.subtopicsTotal} subtopics
                </span>
            </div>
            <div
                class="stack"
                role="img"
                aria-label="{overall.subtopicsMastered} mastered, {overall.subtopicsInProgress} in progress, {overall.subtopicsNotStarted} not started"
            >
                {#if overall.subtopicsMastered > 0}
                    <span
                        class="seg"
                        style="width:{segWidth(
                            overall.subtopicsMastered,
                        )}; background:{GREEN};"
                    ></span>
                {/if}
                {#if overall.subtopicsInProgress > 0}
                    <span
                        class="seg"
                        style="width:{segWidth(
                            overall.subtopicsInProgress,
                        )}; background:{AMBER};"
                    ></span>
                {/if}
                {#if overall.subtopicsNotStarted > 0}
                    <span
                        class="seg"
                        style="width:{segWidth(
                            overall.subtopicsNotStarted,
                        )}; background:{GREY};"
                    ></span>
                {/if}
            </div>
            <div class="overall-legend">
                <span>
                    <b style="color:{GREEN}">{overall.subtopicsMastered}</b>
                    mastered
                </span>
                <span>
                    <b style="color:{AMBER}">{overall.subtopicsInProgress}</b>
                    in progress
                </span>
                <span>
                    <b style="color:{GREY}">{overall.subtopicsNotStarted}</b>
                    not started
                </span>
                <span class="sep">·</span>
                <span>
                    {overall.unitsMastered} / {overall.unitsTotal} units mastered
                </span>
                <span class="sep">·</span>
                <span>{overall.totalReviews} reviews logged</span>
            </div>
            <p class="overall-note">
                This is <b>demonstrated mastery</b>
                — only subtopics you've proven with real reviews (≥ {MIN_PROBLEMS} problems,
                ≥ 80% accurate, ≥ 90% retained) count. It is
                <b>not</b>
                a predicted exam score.
                {#if noScore}
                    Your projected score stays hidden until the give-up threshold is met
                    ({noScore.gradedReviews} / 200 graded reviews, {pct(
                        noScore.coveragePct,
                    )} of the syllabus practiced). Open
                    <b>Readiness</b>
                    from the toolbar for the full breakdown.
                {:else}
                    Open <b>Readiness</b>
                    from the toolbar for your projected score.
                {/if}
            </p>
        </section>
    {/if}

    <div
        class="viewport"
        bind:clientWidth={viewportWidth}
        style="height:{layout.height * scale}px;"
    >
        <div
            class="canvas"
            style="width:{layout.width}px; height:{layout.height}px;
                   transform:scale({scale}); transform-origin:top left;"
        >
            <svg
                class="edges"
                viewBox="0 0 {layout.width} {layout.height}"
                width={layout.width}
                height={layout.height}
            >
                {#each edges as e}
                    <line
                        x1={e.x1}
                        y1={e.y1}
                        x2={e.x2}
                        y2={e.y2}
                        stroke={GREY}
                        stroke-width="2.5"
                        stroke-linecap="round"
                        opacity="0.45"
                    />
                    {#if e.progress > 0}
                        <line
                            x1={e.x1}
                            y1={e.y1}
                            x2={e.x1 + e.progress * (e.x2 - e.x1)}
                            y2={e.y1 + e.progress * (e.y2 - e.y1)}
                            stroke={e.color}
                            stroke-width="3.5"
                            stroke-linecap="round"
                        />
                    {/if}
                {/each}
            </svg>

            <!-- centre -->
            <div
                class="node center"
                style="left:{center.x - center.w / 2}px; top:{center.y -
                    center.h / 2}px;
                       width:{center.w}px; height:{center.h}px;
                       border-color:{ACCENT}; --tint:{ACCENT}1f;"
            >
                <span class="node-title">Exam P</span>
                {#if overall}
                    <span class="node-sub">
                        {overall.subtopicsMastered}/{overall.subtopicsTotal} mastered
                    </span>
                {/if}
            </div>

            <!-- units -->
            {#each units as u}
                {@const up = unitProgress(u.id)}
                {@const uc = colorFor(up, unitMap.get(u.id)?.mastered ?? false)}
                <div
                    class="node unit"
                    style="left:{u.x - u.w / 2}px; top:{u.y - u.h / 2}px;
                           width:{u.w}px; height:{u.h}px;
                           border-color:{uc}; --tint:{uc}1f;"
                >
                    <span class="node-title">{u.name}</span>
                    <span class="node-sub">
                        {unitMap.get(u.id)?.subtopicsCleared ?? 0}/{u.subs.length} mastered
                    </span>
                </div>
            {/each}

            <!-- subtopics -->
            {#each units as u}
                {#each u.subs as s}
                    {@const p = leafProgress(ev(s.tag))}
                    {@const c = colorFor(p, leafCleared(s.tag))}
                    <button
                        class="node leaf"
                        class:selected={selected?.tag === s.tag}
                        style="left:{s.x - s.w / 2}px; top:{s.y - s.h / 2}px;
                               width:{s.w}px; height:{s.h}px;
                               border-color:{c}; --tint:{c}1a;"
                        on:click={() => select(s)}
                    >
                        <span class="node-title">{s.name}</span>
                        <span class="node-sub">{statusLabel(ev(s.tag))}</span>
                    </button>
                {/each}
            {/each}
        </div>
    </div>

    {#if selected}
        {@const m = ev(selected.tag)}
        {@const c = colorFor(leafProgress(m), leafCleared(selected.tag))}
        {@const enough = hasEnoughEvidence(m)}
        <section class="detail">
            <div class="detail-head">
                <div>
                    <h2>{selected.name}</h2>
                    <p class="detail-unit">
                        {units.find((u) => u.id === selected?.unitId)?.name}
                    </p>
                </div>
                <span class="pill" style="background:{c}22; color:{c};">
                    {statusLabel(m)}
                </span>
            </div>
            <dl class="stats">
                <div>
                    <dt>Graded reviews</dt>
                    <dd>
                        {m?.reviews ?? 0}
                        <span class="need">(need ≥ {MIN_PROBLEMS})</span>
                    </dd>
                </div>
                <div>
                    <dt>Accuracy</dt>
                    <dd>
                        {#if enough}
                            {pct(m?.accuracy ?? 0)}
                        {:else}
                            <span class="pending">— need ≥ {MIN_PROBLEMS} reviews</span>
                        {/if}
                        <span class="need">(need ≥ 80%)</span>
                    </dd>
                </div>
                <div>
                    <dt>Mean retrievability</dt>
                    <dd>
                        {#if enough}
                            {pct(m?.meanRetrievability ?? 0)}
                        {:else}
                            <span class="pending">— need ≥ {MIN_PROBLEMS} reviews</span>
                        {/if}
                        <span class="need">(need ≥ 90%)</span>
                    </dd>
                </div>
                <div>
                    <dt>Gate</dt>
                    <dd>{m?.gateCleared ? "cleared" : "not cleared"}</dd>
                </div>
            </dl>
            <p class="hint">
                {#if !m || m.reviews === 0}
                    No reviews yet — study this subtopic from the "SOA Exam P" deck to
                    start building evidence.
                {:else if !enough}
                    Only {m.reviews} of {MIN_PROBLEMS} reviews so far — accuracy and retention
                    stay hidden until there's enough evidence to judge them honestly.
                {:else}
                    Keep reviewing until accuracy ≥ 80% and retention ≥ 90% to clear the
                    gate.
                {/if}
            </p>
        </section>
    {:else}
        <p class="empty-hint">
            Select a subtopic in the map to see its mastery detail.
        </p>
    {/if}
</div>

<style>
    .study-map {
        max-width: 1040px;
        margin: 0 auto;
        padding: 1.5rem 1.25rem 3rem;
        color: var(--fg, #1c1c1e);
        font-size: 15px;
        line-height: 1.45;
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
        margin: 0.5rem 0 0.5rem;
        color: var(--fg-subtle, #4b5563);
        font-size: 0.9rem;
    }
    .key {
        font-size: 0.9rem;
    }
    .notice.error {
        border: 1px solid #d9534f;
        border-radius: 8px;
        padding: 0.75rem 1rem;
        margin-bottom: 1rem;
    }

    /* Overall mastery */
    .overall {
        border: 1px solid var(--border, #e2e2e5);
        border-radius: 10px;
        padding: 0.9rem 1.1rem 1rem;
        margin: 0.25rem 0 1.25rem;
        background: var(--canvas-elevated, #fbfbfc);
    }
    .overall-head {
        display: flex;
        align-items: baseline;
        justify-content: space-between;
        gap: 1rem;
    }
    .overall-head h2 {
        margin: 0;
        font-size: 1.05rem;
    }
    .overall-count {
        font-weight: 700;
        font-size: 0.95rem;
    }
    .stack {
        display: flex;
        height: 12px;
        margin: 0.6rem 0 0.5rem;
        border-radius: 999px;
        overflow: hidden;
        background: var(--canvas-inset, #ececef);
    }
    .stack .seg {
        height: 100%;
    }
    .overall-legend {
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem 0.75rem;
        font-size: 0.82rem;
        color: var(--fg-subtle, #4b5563);
    }
    .overall-legend b {
        font-weight: 700;
    }
    .overall-legend .sep {
        color: var(--border, #cfcfd3);
    }
    .overall-note {
        margin: 0.7rem 0 0;
        font-size: 0.82rem;
        line-height: 1.4;
        color: var(--fg-subtle, #6b7280);
    }
    .viewport {
        position: relative;
        width: 100%;
        overflow: hidden;
    }
    .canvas {
        position: absolute;
        top: 0;
        left: 0;
    }
    .edges {
        position: absolute;
        top: 0;
        left: 0;
        pointer-events: none;
    }
    .node {
        position: absolute;
        box-sizing: border-box;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 2px;
        border: 2px solid var(--border, #e2e2e5);
        border-radius: 12px;
        padding: 4px 8px;
        text-align: center;
        font: inherit;
        color: inherit;
        overflow: hidden;
        background:
            linear-gradient(var(--tint), var(--tint)), var(--canvas-elevated, #fbfbfc);
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
    }
    .node-title {
        font-weight: 600;
        font-size: 0.8rem;
        line-height: 1.12;
    }
    .node-sub {
        font-size: 0.67rem;
        color: var(--fg-subtle, #6b7280);
    }
    .node.center .node-title {
        font-size: 1rem;
        font-weight: 700;
    }
    .node.unit .node-title {
        font-size: 0.88rem;
    }
    button.node.leaf {
        cursor: pointer;
        transition: box-shadow 0.1s ease;
    }
    button.node.leaf:hover {
        box-shadow:
            0 0 0 3px var(--tint),
            0 1px 3px rgba(0, 0, 0, 0.08);
    }
    button.node.leaf.selected {
        box-shadow: 0 0 0 3px var(--fg-subtle, #6b7280);
    }

    /* detail */
    .detail {
        border: 1px solid var(--border, #e2e2e5);
        border-radius: 10px;
        padding: 1rem 1.25rem;
        margin-top: 1.25rem;
        background: var(--canvas-elevated, #fbfbfc);
    }
    .detail-head {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 1rem;
    }
    .detail-head h2 {
        margin: 0;
        font-size: 1.1rem;
    }
    .detail-unit {
        margin: 0.1rem 0 0;
        font-size: 0.8rem;
        color: var(--fg-subtle, #6b7280);
    }
    .pill {
        border-radius: 999px;
        padding: 0.2rem 0.7rem;
        font-size: 0.78rem;
        font-weight: 600;
        white-space: nowrap;
    }
    .stats {
        margin: 0.75rem 0 0;
    }
    .stats > div {
        display: flex;
        justify-content: space-between;
        gap: 1rem;
        padding: 0.45rem 0;
        border-bottom: 1px solid var(--border-subtle, #efeff1);
    }
    .stats > div:last-child {
        border-bottom: none;
    }
    .stats dt {
        color: var(--fg-subtle, #6b7280);
    }
    .stats dd {
        margin: 0;
        font-weight: 600;
    }
    .stats .need {
        font-weight: 400;
        font-size: 0.78rem;
        color: var(--fg-subtle, #9ca3af);
    }
    .stats .pending {
        font-weight: 400;
        font-style: italic;
        color: var(--fg-subtle, #9ca3af);
    }
    .hint {
        margin: 0.75rem 0 0;
        font-size: 0.82rem;
        color: var(--fg-subtle, #6b7280);
    }
    .empty-hint {
        margin-top: 1.25rem;
        color: var(--fg-subtle, #6b7280);
        font-size: 0.9rem;
    }
</style>
