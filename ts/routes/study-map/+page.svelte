<!--
Copyright: Ankitects Pty Ltd and contributors
License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
-->
<script lang="ts">
    import { onMount } from "svelte";

    import { bridgeCommand } from "@tslib/bridgecommand";
    import {
        computeReadiness,
        getMasteryState,
        getStudyPlan,
    } from "@generated/backend";
    import { StudyMode } from "@generated/anki/speedrun_pb";
    import type {
        MasteryState,
        ReadinessResult,
        StudyPlan,
        StudyPlanItem,
        StudyRecommendation,
        SubtopicMastery,
        UnitMastery,
    } from "@generated/anki/speedrun_pb";

    import type { LeafNode, SubtopicEvidence, UnitNode } from "./lib";
    import {
        COLORS,
        computeLayout,
        edgeBetween,
        groupPlanByTier,
        hasEnoughEvidence,
        leafProgress,
        MIN_PROBLEMS,
        statusLabel,
        subtopicTag,
        TAXONOMY,
    } from "./lib";

    const layout = computeLayout();
    const { center, units } = layout;
    const allTags = units.flatMap((u) => u.subs.map((s) => s.tag));

    // Weights mirror pylib/anki/speedrun/exam_p_topics.json, passed to the engine
    // so the weighted mastery rollup and the study priorities line up with the
    // bubble sizes the map draws. Bubble SIZE = importance; bubble FILL = mastery.
    const UNIT_WEIGHTS = TAXONOMY.map((u) => ({
        unitId: u.id,
        weight: u.subtopics.reduce((a, s) => a + s.weight, 0),
    }));
    const SUBTOPIC_WEIGHTS = TAXONOMY.flatMap((u) =>
        u.subtopics.map((s) => ({ tag: subtopicTag(u.id, s.id), weight: s.weight })),
    );
    const NAME_BY_TAG = new Map(
        TAXONOMY.flatMap((u) =>
            u.subtopics.map((s) => [subtopicTag(u.id, s.id), s.name]),
        ),
    );
    const UNIT_NAME_BY_ID = new Map(TAXONOMY.map((u) => [u.id, u.name]));

    const GREY = COLORS.grey;
    const AMBER = COLORS.amber;
    const GREEN = COLORS.green;
    const ACCENT = COLORS.accent;

    let result: MasteryState | null = null;
    let readiness: ReadinessResult | null = null;
    let studyPlan: StudyPlan | null = null;
    let loadError = "";
    let selectedLeaf: LeafNode | null = null;
    let selectedUnit: UnitNode | null = null;

    // Scale the fixed-size diagram to fit the available width (never upscaling).
    // A uniform scale preserves the (verified) non-overlapping geometry.
    let viewportWidth = 0;
    $: scale = viewportWidth > 0 ? Math.min(1, viewportWidth / layout.width) : 1;

    onMount(async () => {
        try {
            [result, readiness, studyPlan] = await Promise.all([
                getMasteryState({
                    expectedSubtopics: allTags,
                    units: UNIT_WEIGHTS,
                    subtopicWeights: SUBTOPIC_WEIGHTS,
                }),
                computeReadiness({ expectedSubtopics: allTags, units: UNIT_WEIGHTS }),
                getStudyPlan({
                    expectedSubtopics: allTags,
                    units: UNIT_WEIGHTS,
                    subtopicWeights: SUBTOPIC_WEIGHTS,
                }),
            ]);
        } catch (err) {
            loadError = String(err);
        }
    });

    $: subMap = new Map<string, SubtopicMastery>(
        (result?.subtopics ?? []).map((s) => [s.tag, s]),
    );
    $: unitMap = new Map<string, UnitMastery>(
        (result?.units ?? []).map((u) => [u.unitId, u]),
    );
    $: overall = result?.overall ?? null;
    $: priorities = result?.priorities ?? [];
    $: recommendation = result?.recommendation ?? null;
    // Today's plan: the decks with something due now, grouped by tier. Counts are
    // Anki's own daily-limit-capped numbers, so they match the deck list.
    $: planGroups = groupPlanByTier(studyPlan?.items ?? []);

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

    function selectLeaf(node: LeafNode): void {
        selectedLeaf = node;
        selectedUnit = null;
    }
    function selectUnit(node: UnitNode): void {
        selectedUnit = node;
        selectedLeaf = null;
    }
    function studySubtopic(tag: string): void {
        // Ask the desktop to open this subtopic's deck for blocked practice.
        bridgeCommand("speedrun-study:" + tag);
    }
    function studyUnit(unitId: string): void {
        // Within-unit interleaving: study the whole unit's deck.
        bridgeCommand("speedrun-study-unit:" + unitId);
    }
    function studyAll(): void {
        // Cross-unit review: study the whole exam deck.
        bridgeCommand("speedrun-study-all");
    }
    function studyRecommended(rec: StudyRecommendation): void {
        if (rec.mode === StudyMode.BLOCKED) {
            studySubtopic(rec.subtopicTag);
        } else if (rec.mode === StudyMode.WITHIN_UNIT) {
            studyUnit(rec.unitId);
        } else {
            studyAll();
        }
    }
    // A plan row points at a real deck id, so open it directly (robust to the
    // display names differing from the deck names).
    function studyDeck(deckId: bigint): void {
        bridgeCommand("speedrun-study-deck:" + deckId);
    }
    function planLabel(it: StudyPlanItem): string {
        if (it.tier === StudyMode.BLOCKED) {
            return NAME_BY_TAG.get(it.subtopicTag) ?? it.deckName;
        }
        if (it.tier === StudyMode.WITHIN_UNIT) {
            return UNIT_NAME_BY_ID.get(it.unitId) ?? it.deckName;
        }
        if (it.tier === StudyMode.CROSS_UNIT) {
            return "Everything (all units)";
        }
        return it.deckName;
    }
    function planCounts(it: StudyPlanItem): string {
        const parts: string[] = [];
        if (it.newCount > 0) {
            parts.push(`${it.newCount} new`);
        }
        if (it.learnCount > 0) {
            parts.push(`${it.learnCount} learning`);
        }
        if (it.reviewCount > 0) {
            parts.push(`${it.reviewCount} due`);
        }
        return parts.join(" · ");
    }
    function recStudyLabel(rec: StudyRecommendation): string {
        switch (rec.mode) {
            case StudyMode.BLOCKED:
                return `Study next: blocked practice · ${NAME_BY_TAG.get(rec.subtopicTag) ?? rec.subtopicTag}`;
            case StudyMode.WITHIN_UNIT:
                return `Study next: within-unit interleaving · ${UNIT_NAME_BY_ID.get(rec.unitId) ?? rec.unitId}`;
            case StudyMode.CROSS_UNIT:
                return "Study next: cross-unit review (everything)";
            default:
                return "Review everything (all subtopics mastered)";
        }
    }
</script>

<div class="study-map">
    <header>
        <h1>Study map</h1>
        <p class="exam">SOA Exam P · Probability</p>
        <p class="subtitle">
            Each bubble is a topic. Its <b>size</b>
            is that topic's weight on the exam; its
            <b>colour</b>
            fills as you clear its mastery gate:
            <span class="key" style="color:{GREY}">●</span>
            not started,
            <span class="key" style="color:{AMBER}">●</span>
            in progress,
            <span class="key" style="color:{GREEN}">●</span>
            mastered. Colour is measured from real reviews, never guessed.
        </p>
    </header>

    {#if loadError}
        <div class="notice error">Couldn't load mastery: {loadError}</div>
    {/if}

    {#if studyPlan}
        <section class="plan" aria-label="Today's study plan">
            <div class="plan-head">
                <h2>Today's plan</h2>
                <span class="plan-sub">the decks to study now, grouped by tier</span>
            </div>
            {#if planGroups.length === 0}
                <p class="plan-empty">
                    Nothing due today — you're caught up. Add new cards or come back
                    tomorrow.
                </p>
            {:else}
                {#each planGroups as g}
                    <div class="tier">
                        <div class="tier-head">
                            <span
                                class="tier-dot"
                                style="background:{g.meta.color}"
                            ></span>
                            <b>{g.meta.label}</b>
                            <span class="tier-blurb">{g.meta.blurb}</span>
                        </div>
                        {#each g.items as it}
                            <div class="plan-row">
                                <span class="plan-label">{planLabel(it)}</span>
                                <span class="plan-count">{planCounts(it)}</span>
                                <button
                                    class="plan-study"
                                    style="border-color:{g.meta.color}; color:{g.meta
                                        .color};"
                                    on:click={() => studyDeck(it.deckId)}
                                >
                                    Study
                                </button>
                            </div>
                        {/each}
                    </div>
                {/each}
                <p class="plan-note">
                    Counts are today's cards after Anki's daily limits — the same
                    numbers as the deck list. Blocked rows show a subtopic's own cards;
                    higher tiers unlock as you clear gates.
                </p>
            {/if}
        </section>
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
                <span>
                    <b>{pct(overall.weightedMasteryPct)}</b>
                    by exam weight
                </span>
            </div>
            {#if priorities.length > 0}
                <p class="focus">
                    <span class="focus-label">Weakest</span>
                    <b>
                        {NAME_BY_TAG.get(priorities[0].tag) ?? priorities[0].subtopicId}
                    </b>
                    — {priorities[0].reason}
                </p>
            {/if}
            {#if recommendation}
                {@const rec = recommendation}
                <button class="study-btn" on:click={() => studyRecommended(rec)}>
                    {recStudyLabel(rec)}
                </button>
                <button class="study-btn secondary" on:click={studyAll}>
                    Study everything (cross-unit review)
                </button>
            {/if}
            <p class="overall-note">
                This is <b>demonstrated mastery</b>
                — only subtopics you've proven with real reviews (≥ {MIN_PROBLEMS} problems,
                ≥ 80% accurate, ≥ 90% retained) count, and "{pct(
                    overall.weightedMasteryPct,
                )} by exam weight" weights them by section importance. It is
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
                        opacity="0.4"
                    />
                    {#if e.progress > 0}
                        <line
                            x1={e.x1}
                            y1={e.y1}
                            x2={e.x1 + e.progress * (e.x2 - e.x1)}
                            y2={e.y1 + e.progress * (e.y2 - e.y1)}
                            stroke={e.color}
                            stroke-width="4"
                            stroke-linecap="round"
                        />
                    {/if}
                {/each}
            </svg>

            <!-- centre -->
            <div
                class="bubble center"
                style="left:{center.x - center.r}px; top:{center.y - center.r}px;
                       width:{center.r * 2}px; height:{center.r * 2}px;
                       border-color:{ACCENT}; --tint:{ACCENT}1f;"
            >
                <span class="node-title">Exam P</span>
                {#if overall}
                    <span class="node-sub">
                        {overall.subtopicsMastered}/{overall.subtopicsTotal}
                    </span>
                {/if}
            </div>

            <!-- units -->
            {#each units as u}
                {@const up = unitProgress(u.id)}
                {@const uc = colorFor(up, unitMap.get(u.id)?.mastered ?? false)}
                <button
                    class="bubble unit"
                    class:selected={selectedUnit?.id === u.id}
                    style="left:{u.x - u.r}px; top:{u.y - u.r}px;
                           width:{u.r * 2}px; height:{u.r * 2}px;
                           border-color:{uc}; --tint:{uc}1f;"
                    on:click={() => selectUnit(u)}
                >
                    <span class="node-title">{u.name}</span>
                    <span class="node-sub">
                        {unitMap.get(u.id)?.subtopicsCleared ?? 0}/{u.subs.length} mastered
                    </span>
                </button>
            {/each}

            <!-- subtopics: bubble sized by weight, name label beneath -->
            {#each units as u}
                {#each u.subs as s}
                    {@const p = leafProgress(ev(s.tag))}
                    {@const c = colorFor(p, leafCleared(s.tag))}
                    <button
                        class="leaf"
                        class:selected={selectedLeaf?.tag === s.tag}
                        style="left:{s.x - 48}px; top:{s.y - s.r}px; width:96px;"
                        title="{s.name} · exam weight {s.weight.toFixed(1)}"
                        on:click={() => selectLeaf(s)}
                    >
                        <span
                            class="leaf-bubble"
                            style="width:{s.r * 2}px; height:{s.r * 2}px;
                                   border-color:{c}; --tint:{c}1a;"
                        ></span>
                        <span class="caption">{s.name}</span>
                    </button>
                {/each}
            {/each}
        </div>
    </div>

    {#if selectedUnit}
        {@const um = unitMap.get(selectedUnit.id)}
        {@const uc = colorFor(unitProgress(selectedUnit.id), um?.mastered ?? false)}
        {@const unitId = selectedUnit.id}
        <section class="detail">
            <div class="detail-head">
                <div>
                    <h2>{selectedUnit.name}</h2>
                    <p class="detail-unit">Unit · one of the three exam sections</p>
                </div>
                <span class="pill" style="background:{uc}22; color:{uc};">
                    {um?.subtopicsCleared ?? 0}/{um?.subtopicsTotal ??
                        selectedUnit.subs.length} mastered
                </span>
            </div>
            <dl class="stats">
                <div>
                    <dt>Subtopics mastered</dt>
                    <dd>{um?.subtopicsCleared ?? 0} / {um?.subtopicsTotal ?? 0}</dd>
                </div>
                <div>
                    <dt>Exam importance</dt>
                    <dd>{(um?.weight ?? selectedUnit.weight).toFixed(1)} of 100</dd>
                </div>
                <div>
                    <dt>Mastery by weight</dt>
                    <dd>{pct(um?.weightedMasteryPct ?? 0)}</dd>
                </div>
                <div>
                    <dt>Interleaving tier</dt>
                    <dd>{um?.mastered ? "cross-unit (spacing)" : "within-unit"}</dd>
                </div>
            </dl>
            <p class="hint">
                "Mastery by weight" is the share of this unit's exam importance you've
                demonstrably mastered — measured from real reviews, not a predicted
                score.
            </p>
            <button class="study-btn" on:click={() => studyUnit(unitId)}>
                Study this unit (within-unit interleaving)
            </button>
        </section>
    {:else if selectedLeaf}
        {@const m = ev(selectedLeaf.tag)}
        {@const c = colorFor(leafProgress(m), leafCleared(selectedLeaf.tag))}
        {@const enough = hasEnoughEvidence(m)}
        {@const studyTag = selectedLeaf.tag}
        <section class="detail">
            <div class="detail-head">
                <div>
                    <h2>{selectedLeaf.name}</h2>
                    <p class="detail-unit">
                        {units.find((u) => u.id === selectedLeaf?.unitId)?.name} · exam weight
                        {selectedLeaf.weight.toFixed(1)}
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
            <button class="study-btn" on:click={() => studySubtopic(studyTag)}>
                Study this subtopic (blocked practice)
            </button>
        </section>
    {:else}
        <p class="empty-hint">
            Select a unit or subtopic in the map to see its mastery detail.
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
        font-size: 0.95rem;
        vertical-align: middle;
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
    .focus {
        margin: 0.7rem 0 0;
        font-size: 0.86rem;
        display: flex;
        align-items: baseline;
        flex-wrap: wrap;
        gap: 0.4rem;
    }
    .focus-label {
        font-size: 0.68rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: var(--fg-subtle, #6b7280);
        background: var(--canvas-inset, #ececef);
        border-radius: 999px;
        padding: 0.1rem 0.5rem;
    }
    .overall-note {
        margin: 0.7rem 0 0;
        font-size: 0.82rem;
        line-height: 1.4;
        color: var(--fg-subtle, #6b7280);
    }

    /* Today's plan */
    .plan {
        border: 1px solid var(--border, #e2e2e5);
        border-radius: 10px;
        padding: 0.9rem 1.1rem 1rem;
        margin: 0.25rem 0 1.25rem;
        background: var(--canvas-elevated, #fbfbfc);
    }
    .plan-head {
        display: flex;
        align-items: baseline;
        justify-content: space-between;
        gap: 1rem;
    }
    .plan-head h2 {
        margin: 0;
        font-size: 1.05rem;
    }
    .plan-sub {
        font-size: 0.8rem;
        color: var(--fg-subtle, #6b7280);
    }
    .plan-empty {
        margin: 0.6rem 0 0;
        font-size: 0.88rem;
        color: var(--fg-subtle, #4b5563);
    }
    .tier {
        margin-top: 0.85rem;
    }
    .tier-head {
        display: flex;
        align-items: baseline;
        flex-wrap: wrap;
        gap: 0.4rem;
        margin-bottom: 0.3rem;
    }
    .tier-dot {
        width: 9px;
        height: 9px;
        border-radius: 50%;
        align-self: center;
    }
    .tier-blurb {
        font-size: 0.78rem;
        color: var(--fg-subtle, #6b7280);
    }
    .plan-row {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        padding: 0.4rem 0;
        border-bottom: 1px solid var(--border-subtle, #efeff1);
    }
    .tier .plan-row:last-child {
        border-bottom: none;
    }
    .plan-label {
        flex: 1 1 auto;
        font-weight: 600;
        font-size: 0.9rem;
    }
    .plan-count {
        flex: 0 0 auto;
        font-size: 0.8rem;
        color: var(--fg-subtle, #6b7280);
        white-space: nowrap;
    }
    .plan-study {
        flex: 0 0 auto;
        padding: 0.3rem 0.85rem;
        border: 1px solid var(--border, #c7c7cc);
        border-radius: 7px;
        background: transparent;
        font: inherit;
        font-weight: 600;
        font-size: 0.82rem;
        cursor: pointer;
    }
    .plan-study:hover {
        filter: brightness(0.96);
        background: var(--canvas-inset, #f0f1f3);
    }
    .plan-note {
        margin: 0.8rem 0 0;
        font-size: 0.78rem;
        line-height: 1.4;
        color: var(--fg-subtle, #9ca3af);
    }

    /* Concept map */
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

    /* Round bubbles (centre + units) */
    .bubble {
        position: absolute;
        box-sizing: border-box;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 1px;
        border: 2.5px solid var(--border, #e2e2e5);
        border-radius: 50%;
        padding: 4px;
        text-align: center;
        font: inherit;
        color: inherit;
        overflow: hidden;
        background:
            linear-gradient(var(--tint), var(--tint)), var(--canvas-elevated, #fbfbfc);
        box-shadow: 0 1px 4px rgba(0, 0, 0, 0.07);
    }
    .node-title {
        font-weight: 600;
        font-size: 0.78rem;
        line-height: 1.1;
    }
    .node-sub {
        font-size: 0.64rem;
        color: var(--fg-subtle, #6b7280);
    }
    .bubble.center .node-title {
        font-size: 1rem;
        font-weight: 700;
    }
    .bubble.unit {
        cursor: pointer;
        transition:
            box-shadow 0.12s ease,
            transform 0.12s ease;
    }
    .bubble.unit .node-title {
        font-size: 0.82rem;
    }
    .bubble.unit:hover {
        box-shadow:
            0 0 0 3px var(--tint),
            0 2px 6px rgba(0, 0, 0, 0.1);
    }
    .bubble.unit.selected {
        box-shadow: 0 0 0 3px var(--fg-subtle, #6b7280);
    }

    /* Subtopic: a circular bubble with the name beneath it */
    .leaf {
        position: absolute;
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 3px;
        background: none;
        border: none;
        padding: 0;
        font: inherit;
        color: inherit;
        cursor: pointer;
    }
    .leaf-bubble {
        box-sizing: border-box;
        border: 2.5px solid var(--border, #e2e2e5);
        border-radius: 50%;
        background:
            linear-gradient(var(--tint), var(--tint)), var(--canvas-elevated, #fbfbfc);
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
        transition:
            box-shadow 0.12s ease,
            transform 0.12s ease;
    }
    .leaf:hover .leaf-bubble {
        box-shadow:
            0 0 0 3px var(--tint),
            0 2px 6px rgba(0, 0, 0, 0.1);
        transform: scale(1.04);
    }
    .leaf.selected .leaf-bubble {
        box-shadow: 0 0 0 3px var(--fg-subtle, #6b7280);
    }
    .caption {
        font-size: 0.68rem;
        line-height: 1.12;
        text-align: center;
        color: var(--fg, #33373d);
        max-width: 96px;
    }
    .leaf.selected .caption {
        font-weight: 600;
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
    .study-btn {
        margin-top: 0.9rem;
        width: 100%;
        padding: 0.55rem 0.75rem;
        border: none;
        border-radius: 8px;
        background: #6486bf;
        color: #fff;
        font: inherit;
        font-weight: 600;
        cursor: pointer;
    }
    .study-btn:hover {
        filter: brightness(1.05);
    }
    .study-btn.secondary {
        margin-top: 0.5rem;
        background: transparent;
        color: #6486bf;
        border: 1px solid #6486bf;
    }
    .empty-hint {
        margin-top: 1.25rem;
        color: var(--fg-subtle, #6b7280);
        font-size: 0.9rem;
    }

    /* Calm by default: honour reduced-motion preferences. */
    @media (prefers-reduced-motion: reduce) {
        .bubble.unit,
        .leaf-bubble {
            transition: none;
        }
        .leaf:hover .leaf-bubble {
            transform: none;
        }
    }
</style>
