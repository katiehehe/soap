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
        getStudyPace,
        getStudyPlan,
    } from "@generated/backend";
    import { StudyMode } from "@generated/anki/speedrun_pb";
    import type {
        MasteryState,
        ReadinessResult,
        StudyPace,
        StudyPlan,
        StudyPlanItem,
        StudyRecommendation,
        SubtopicMastery,
        UnitMastery,
    } from "@generated/anki/speedrun_pb";

    import type {
        LeafNode,
        PaceView,
        PrereqEdge,
        SubtopicEvidence,
        UnitNode,
    } from "./lib";
    import {
        arrowHead,
        COLORS,
        computeLayout,
        edgeBetween,
        groupPlanByTier,
        hasEnoughEvidence,
        leafProgress,
        MIN_PROBLEMS,
        paceTone,
        prereqChain,
        prereqEdges,
        statusLabel,
        subtopicTag,
        TAXONOMY,
        UNIT_PREREQS,
    } from "./lib";

    const layout = computeLayout();
    const { center, units } = layout;
    const allTags = units.flatMap((u) => u.subs.map((s) => s.tag));
    // Directed prerequisite arrows, computed once from the fixed geometry.
    const prereqArrows = prereqEdges(layout);
    // "Show prerequisites" is on by default so the guided order is visible.
    let showPrereqs = true;

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

    // The guided-learning DAG, sent to the engine so what the map draws and what
    // the scheduler gates on come from one source. Curriculum order only.
    const SUBTOPIC_PREREQS = TAXONOMY.flatMap((u) =>
        u.subtopics.map((s) => ({
            tag: subtopicTag(u.id, s.id),
            prereqs: s.prereqs.map((p) => subtopicTag(u.id, p)),
        })),
    );
    const UNIT_PREREQS_REQ = TAXONOMY.map((u) => ({
        unitId: u.id,
        prereqs: UNIT_PREREQS[u.id] ?? [],
    }));

    const GREY = COLORS.grey;
    const AMBER = COLORS.amber;
    const GREEN = COLORS.green;
    const ACCENT = COLORS.accent;

    // Which sections to render. The home shell shows the map on the Concept map
    // tab (variant "map") and the plan/pace/mastery panels on the Progress tab
    // (variant "panels"); the standalone /study-map route shows everything.
    export let variant: "map" | "panels" | "full" = "full";
    $: showMap = variant !== "panels";
    $: showPanels = variant !== "map";

    let result: MasteryState | null = null;
    let readiness: ReadinessResult | null = null;
    let studyPlan: StudyPlan | null = null;
    let pace: StudyPace | null = null;
    let loadError = "";
    let selectedLeaf: LeafNode | null = null;
    let selectedUnit: UnitNode | null = null;

    // Scale the fixed-size diagram to fit the available width (never upscaling).
    // A uniform scale preserves the (verified) non-overlapping geometry. The
    // compact geometry (see lib.ts) means scale stays at/near 1 on a normal
    // window, so the bubble labels render at their intended (readable) size.
    let viewportWidth = 0;
    $: scale = viewportWidth > 0 ? Math.min(1, viewportWidth / layout.width) : 1;
    // Centre the diagram when the viewport is wider than the scaled canvas.
    $: canvasLeft = Math.max(0, (viewportWidth - layout.width * scale) / 2);

    async function loadState(): Promise<void> {
        try {
            [result, readiness, studyPlan, pace] = await Promise.all([
                getMasteryState({
                    expectedSubtopics: allTags,
                    units: UNIT_WEIGHTS,
                    subtopicWeights: SUBTOPIC_WEIGHTS,
                    subtopicPrereqs: SUBTOPIC_PREREQS,
                    unitPrereqs: UNIT_PREREQS_REQ,
                }),
                computeReadiness({ expectedSubtopics: allTags, units: UNIT_WEIGHTS }),
                getStudyPlan({
                    expectedSubtopics: allTags,
                    units: UNIT_WEIGHTS,
                    subtopicWeights: SUBTOPIC_WEIGHTS,
                    subtopicPrereqs: SUBTOPIC_PREREQS,
                    unitPrereqs: UNIT_PREREQS_REQ,
                }),
                getStudyPace({
                    expectedSubtopics: allTags,
                    units: UNIT_WEIGHTS,
                    subtopicWeights: SUBTOPIC_WEIGHTS,
                    subtopicPrereqs: SUBTOPIC_PREREQS,
                    unitPrereqs: UNIT_PREREQS_REQ,
                }),
            ]);
        } catch (err) {
            loadError = String(err);
        }
    }
    onMount(loadState);

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

    // "Today's focus": the subtopics genuinely worth highlighting right now —
    // ones with cards DUE today (blocked practice, straight from the scheduler)
    // plus your current single weakest/highest-priority subtopic. All MEASURED,
    // never fabricated; it changes as cards fall due and mastery moves. Shown
    // only once there's real study signal, so a brand-new deck stays quiet.
    $: hasStudyActivity =
        (studyPlan?.items?.length ?? 0) > 0 || (overall?.totalReviews ?? 0) > 0;
    $: focusTags = (() => {
        const tags = new Set<string>();
        if (!hasStudyActivity) {
            return tags;
        }
        // Subtopics with cards due today (blocked-practice tier).
        for (const it of studyPlan?.items ?? []) {
            if (it.tier === StudyMode.BLOCKED && it.subtopicTag) {
                tags.add(it.subtopicTag);
            }
        }
        // Plus your current weakest / highest-priority subtopic.
        if (priorities.length > 0) {
            tags.add(priorities[0].tag);
        }
        return tags;
    })();
    $: focusList = [...focusTags]
        .map((t) => ({ tag: t, name: NAME_BY_TAG.get(t) ?? t }))
        .slice(0, 6);

    // Exam-coverage pace (are you introducing new cards fast enough?). All values
    // are measured counts / arithmetic — a coverage pace, never a score.
    $: paceView = pace
        ? ({
              hasExamDate: pace.hasExamDate,
              daysLeft: Number(pace.daysLeft),
              remainingNew: pace.remainingNew,
              currentNewPerDay: pace.currentNewPerDay,
              recommendedNewPerDay: pace.recommendedNewPerDay,
              projectedDaysToFinish: pace.projectedDaysToFinish,
              onTrack: pace.onTrack,
          } satisfies PaceView)
        : null;
    $: paceState = paceView ? paceTone(paceView) : "none";
    // Noon-anchored timestamp -> the exam day is stable across time zones.
    $: examIso = paceView?.hasExamDate
        ? new Date(Number(pace!.examTimestamp) * 1000).toISOString().slice(0, 10)
        : "";

    // Honest readiness give-up state — never a fabricated number. The score
    // itself lives on the Readiness page; here we only surface why it's withheld.
    $: noScore = readiness?.value.case === "noScore" ? readiness.value.value : null;

    // Guided-learning gate state from the engine (mirrors config
    // speedrunGuidedMode; default on). Drives the "Guided sequence" toggle.
    $: guidedMode = result?.guidedMode ?? true;

    // Selecting a subtopic highlights its prerequisite CHAIN: ancestors (do
    // these first) and descendants (these unlock afterwards).
    $: chain = selectedLeaf ? prereqChain(selectedLeaf.tag) : null;
    $: highlightSet = (() => {
        const s = new Set<string>();
        if (selectedLeaf) {
            s.add(selectedLeaf.tag);
            chain?.ancestors.forEach((t) => s.add(t));
            chain?.descendants.forEach((t) => s.add(t));
        }
        return s;
    })();
    // Reactive set of guided-locked subtopic tags, so lock badges/dimming
    // re-render the moment mastery state loads (a plain function call wouldn't
    // create the dependency).
    $: lockedSet = new Set<string>(
        (result?.subtopics ?? []).filter((s) => s.locked).map((s) => s.tag),
    );

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
    function closeDetail(): void {
        selectedLeaf = null;
        selectedUnit = null;
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
    // Exam-pace actions (all go through the desktop bridge).
    function onExamDateInput(e: Event): void {
        const value = (e.currentTarget as HTMLInputElement).value;
        if (value) {
            bridgeCommand("speedrun-set-exam-date:" + value);
        } else {
            bridgeCommand("speedrun-clear-exam-date");
        }
    }
    function clearExamDate(): void {
        bridgeCommand("speedrun-clear-exam-date");
    }
    function raiseNewPerDay(n: number): void {
        // Permanent "get on track" lever: raise the exam deck's daily new limit.
        bridgeCommand("speedrun-set-new-per-day:" + n);
    }
    function studyMore(): void {
        // "Go ahead" beyond today's quota: extend today's new limit and study.
        bridgeCommand("speedrun-extend-new:20");
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

    // --- guided gate: locks, prerequisite highlight, bypasses ---
    function arrowActive(e: PrereqEdge): boolean {
        return !!selectedLeaf && highlightSet.has(e.from) && highlightSet.has(e.to);
    }
    function unmetNames(m: SubtopicMastery): string[] {
        return (m.unmetPrereqs ?? []).map((t) => NAME_BY_TAG.get(t) ?? t);
    }
    function setGuided(on: boolean): void {
        // Global bypass ("free mode"): turn the hard prerequisite gate on/off.
        bridgeCommand("speedrun-set-guided:" + (on ? "1" : "0"));
        // Re-read state after the desktop writes the config.
        setTimeout(loadState, 150);
    }
    function unlockSubtopic(tag: string): void {
        // Per-topic bypass for experienced users.
        bridgeCommand("speedrun-unlock:" + tag);
        setTimeout(loadState, 150);
    }
    // Prerequisite-arrow styling (helpers keep the markup free of nested ternaries).
    function arrowColor(active: boolean): string {
        return active ? ACCENT : "#94a3b8";
    }
    function arrowLineOpacity(dim: boolean, active: boolean): number {
        if (dim) {
            return 0.1;
        }
        return active ? 0.95 : 0.32;
    }
    function arrowFillOpacity(dim: boolean, active: boolean): number {
        if (dim) {
            return 0.1;
        }
        return active ? 0.95 : 0.42;
    }
</script>

<div class="study-map">
    {#if showMap}
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
    {/if}

    {#if showMap}
        <div class="map-controls">
            <label class="ctrl">
                <input type="checkbox" bind:checked={showPrereqs} />
                Show prerequisites
            </label>
            <label class="ctrl">
                <input
                    type="checkbox"
                    checked={guidedMode}
                    on:change={(e) => setGuided(e.currentTarget.checked)}
                />
                Guided sequence:
                <b>{guidedMode ? "on" : "off"}</b>
            </label>
            <span class="ctrl-hint">
                Guided sequence locks a topic's new cards until its prerequisites are
                met (its memory gate OR a practice test). Turn it off to study any topic
                freely.
            </span>
        </div>
    {/if}

    {#if loadError}
        <div class="notice error">Couldn't load mastery: {loadError}</div>
    {/if}

    {#if showMap && focusList.length > 0}
        <section class="focus-strip" aria-label="Today's focus">
            <div class="focus-strip-head">
                <span class="focus-badge">Today's focus</span>
                <span class="focus-hint">
                    highlighted on the map · due now + your weakest area
                </span>
            </div>
            <div class="focus-chips">
                {#each focusList as f}
                    <button class="focus-chip" on:click={() => studySubtopic(f.tag)}>
                        {f.name}
                    </button>
                {/each}
            </div>
        </section>
    {/if}

    {#if showPanels && studyPlan}
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
            <button class="plan-more" on:click={studyMore}>
                Study more today (+20 new cards)
            </button>
        </section>
    {/if}

    {#if showPanels && pace}
        <section class="pace" aria-label="Exam pace">
            <div class="pace-head">
                <h2>Exam pace</h2>
                {#if paceState === "ok"}
                    <span class="pace-badge ok">On track</span>
                {:else if paceState === "behind"}
                    <span class="pace-badge behind">Behind</span>
                {:else if paceState === "past"}
                    <span class="pace-badge past">Date passed</span>
                {/if}
            </div>

            <div class="pace-row">
                <label class="pace-date">
                    Exam date
                    <input type="date" value={examIso} on:change={onExamDateInput} />
                </label>
                {#if paceView?.hasExamDate}
                    <button class="pace-clear" on:click={clearExamDate}>Clear</button>
                {/if}
            </div>

            {#if paceView && paceView.hasExamDate}
                {#if paceState === "past"}
                    <p class="pace-detail">
                        Your exam date has passed — set a new one to track pace.
                    </p>
                {:else}
                    <p class="pace-detail">
                        <b>{paceView.daysLeft}</b>
                        days left ·
                        <b>{paceView.remainingNew}</b>
                        new cards left · at your current
                        <b>{paceView.currentNewPerDay}/day</b>
                        you'd finish introducing them in
                        <b>{paceView.projectedDaysToFinish || "—"}</b>
                        days.
                    </p>
                    {#if !paceView.onTrack && paceView.remainingNew > 0}
                        <p class="pace-fix">
                            To cover everything in time, aim for about
                            <b>{paceView.recommendedNewPerDay}/day</b>
                            .
                            <button
                                class="pace-raise"
                                on:click={() =>
                                    raiseNewPerDay(paceView.recommendedNewPerDay)}
                            >
                                Raise daily new to {paceView.recommendedNewPerDay}
                            </button>
                        </p>
                    {/if}
                {/if}
            {:else}
                <p class="pace-detail">
                    Set your exam date to see if you're introducing new cards fast
                    enough to cover the syllabus in time. This is a
                    <b>coverage pace</b>
                    , not a predicted score.
                </p>
            {/if}
        </section>
    {/if}

    {#if showPanels && overall}
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

    {#if showMap}
        <div class="map-card">
            <div
                class="viewport"
                bind:clientWidth={viewportWidth}
                style="height:{layout.height * scale}px;"
            >
                <div
                    class="canvas"
                    style="width:{layout.width}px; height:{layout.height}px;
                   left:{canvasLeft}px; transform:scale({scale}); transform-origin:top left;"
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

                    <!-- directed prerequisite arrows (the guided-learning DAG) -->
                    {#if showPrereqs}
                        {#each prereqArrows as a}
                            {@const active = arrowActive(a)}
                            {@const dim = !!selectedLeaf && !active}
                            <line
                                x1={a.geom.x1}
                                y1={a.geom.y1}
                                x2={a.geom.x2}
                                y2={a.geom.y2}
                                stroke={arrowColor(active)}
                                stroke-width={active ? 2.5 : 1.5}
                                stroke-dasharray="5 4"
                                opacity={arrowLineOpacity(dim, active)}
                            />
                            <polygon
                                points={arrowHead(a.geom, a.kind === "unit" ? 14 : 11)}
                                fill={arrowColor(active)}
                                opacity={arrowFillOpacity(dim, active)}
                            />
                        {/each}
                    {/if}
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
                        <span class="node-pct">{Math.round(u.weight)}% of exam</span>
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
                            class:focus={focusTags.has(s.tag)}
                            class:locked={lockedSet.has(s.tag)}
                            class:dim={selectedLeaf && !highlightSet.has(s.tag)}
                            style="left:{s.x - s.r}px; top:{s.y - s.r}px;
                               width:{s.r * 2}px; height:{s.r * 2}px;
                               border-color:{c}; --tint:{c}1a;"
                            title="{s.name} · exam weight {s.weight.toFixed(
                                1,
                            )}{lockedSet.has(s.tag)
                                ? ' · locked (prerequisites not met)'
                                : ''}"
                            on:click={() => selectLeaf(s)}
                        >
                            <span class="leaf-label">{s.name}</span>
                            {#if lockedSet.has(s.tag)}
                                <span class="lock-badge" aria-label="locked">🔒</span>
                            {/if}
                        </button>
                    {/each}
                {/each}
                </div>
            </div>
        </div>
    {/if}

    {#if showMap && (selectedUnit || selectedLeaf)}
        <section class="detail detail-popup">
            <button
                class="detail-close"
                on:click={closeDetail}
                aria-label="Close detail"
            >
                ×
            </button>
            {#if selectedUnit}
                {@const um = unitMap.get(selectedUnit.id)}
                {@const uc = colorFor(
                    unitProgress(selectedUnit.id),
                    um?.mastered ?? false,
                )}
                {@const unitId = selectedUnit.id}
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
                    "Mastery by weight" is the share of this unit's exam importance
                    you've demonstrably mastered — measured from real reviews, not a
                    predicted score.
                </p>
                <button class="study-btn" on:click={() => studyUnit(unitId)}>
                    Study this unit (within-unit interleaving)
                </button>
            {:else if selectedLeaf}
                {@const m = ev(selectedLeaf.tag)}
                {@const full = subMap.get(selectedLeaf.tag)}
                {@const c = colorFor(leafProgress(m), leafCleared(selectedLeaf.tag))}
                {@const enough = hasEnoughEvidence(m)}
                {@const studyTag = selectedLeaf.tag}
                <div class="detail-head">
                    <div>
                        <h2>{selectedLeaf.name}</h2>
                        <p class="detail-unit">
                            {units.find((u) => u.id === selectedLeaf?.unitId)?.name} · exam
                            weight
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
                                <span class="pending">
                                    — need ≥ {MIN_PROBLEMS} reviews
                                </span>
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
                                <span class="pending">
                                    — need ≥ {MIN_PROBLEMS} reviews
                                </span>
                            {/if}
                            <span class="need">(need ≥ 90%)</span>
                        </dd>
                    </div>
                    <div>
                        <dt>Gate</dt>
                        <dd>{m?.gateCleared ? "cleared" : "not cleared"}</dd>
                    </div>
                </dl>

                <!-- Performance: a SEPARATE signal from the memory gate above.
                     Never blended into mastery (kept apart per the rubric). -->
                <div class="perf">
                    <div class="perf-head">
                        <span class="perf-title">Performance (practice tests)</span>
                        <span class="perf-sep">separate from the memory gate</span>
                    </div>
                    {#if full && full.perfQuestions > 0}
                        <div class="perf-body">
                            <b>{pct(full.perfAccuracy)}</b>
                            <span class="need">
                                {full.perfCorrect}/{full.perfQuestions} questions{full.performanceMastered
                                    ? " · mastered"
                                    : ""}
                            </span>
                        </div>
                    {:else}
                        <div class="perf-body pending">
                            No graded practice questions yet — take a practice test to
                            build this signal.
                        </div>
                    {/if}
                </div>

                {#if full?.locked}
                    <div class="lock-note">
                        <b>🔒 Locked by guided sequence.</b>
                        First master {unmetNames(full).join(", ") ||
                            "its prerequisites"} — or clear it on a practice test.
                        <button
                            class="unlock-btn"
                            on:click={() => unlockSubtopic(studyTag)}
                        >
                            Unlock anyway
                        </button>
                    </div>
                {/if}
                <p class="hint">
                    {#if !m || m.reviews === 0}
                        No reviews yet — study this subtopic from the "SOA Exam P" deck
                        to start building evidence.
                    {:else if !enough}
                        Only {m.reviews} of {MIN_PROBLEMS} reviews so far — accuracy and retention
                        stay hidden until there's enough evidence to judge them honestly.
                    {:else}
                        Keep reviewing until accuracy ≥ 80% and retention ≥ 90% to clear
                        the gate.
                    {/if}
                </p>
                <button class="study-btn" on:click={() => studySubtopic(studyTag)}>
                    Study this subtopic (blocked practice)
                </button>
            {/if}
        </section>
    {/if}
</div>

<style>
    .study-map {
        max-width: 1180px;
        margin: 0 auto;
        padding: 1.75rem 1.5rem 3rem;
        color: var(--fg, #1c1c1e);
        font-size: 15px;
        line-height: 1.5;
    }
    header {
        margin-bottom: 1.25rem;
    }
    header h1 {
        margin: 0;
        font-size: 1.7rem;
        font-weight: 800;
        letter-spacing: -0.01em;
    }
    header .exam {
        margin: 0.25rem 0 0;
        font-size: 0.8rem;
        font-weight: 700;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: var(--sr-accent, #6366f1);
    }
    header .subtitle {
        margin: 0.6rem 0 0;
        max-width: 68ch;
        color: var(--fg-subtle, #4b5563);
        font-size: 0.92rem;
        line-height: 1.55;
    }
    .key {
        font-size: 1rem;
        vertical-align: middle;
    }
    .notice.error {
        border: 1px solid #d9534f;
        border-radius: 8px;
        padding: 0.75rem 1rem;
        margin-bottom: 1rem;
    }

    /* Map controls: show-prerequisites + guided-sequence toggles */
    .map-controls {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 0.6rem 1.25rem;
        margin: 0 0 1.25rem;
        padding: 0.7rem 1.1rem;
        border: 1px solid var(--border, #e6e7eb);
        border-radius: 14px;
        background: var(--canvas-elevated, #fff);
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
        font-size: 0.88rem;
    }
    .map-controls .ctrl {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        cursor: pointer;
        font-weight: 600;
        white-space: nowrap;
    }
    .map-controls .ctrl input {
        cursor: pointer;
    }
    .ctrl-hint {
        flex: 1 1 240px;
        font-size: 0.76rem;
        font-weight: 400;
        color: var(--fg-subtle, #6b7280);
    }

    /* Today's focus strip */
    .focus-strip {
        border: 1px solid var(--border, #e6e7eb);
        border-radius: 14px;
        padding: 1rem 1.25rem;
        margin: 0 0 1.25rem;
        background: var(--canvas-elevated, #fff);
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
    }
    .focus-strip-head {
        display: flex;
        align-items: baseline;
        gap: 0.5rem;
        flex-wrap: wrap;
        margin-bottom: 0.5rem;
    }
    .focus-badge {
        font-size: 0.68rem;
        font-weight: 800;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: var(--sr-accent, #6366f1);
        background: var(--sr-accent-weak, rgba(99, 102, 241, 0.12));
        border-radius: 999px;
        padding: 0.15rem 0.55rem;
    }
    .focus-hint {
        font-size: 0.78rem;
        color: var(--fg-subtle, #6b7280);
    }
    .focus-chips {
        display: flex;
        flex-wrap: wrap;
        gap: 0.4rem;
    }
    .focus-chip {
        border: 1px solid var(--sr-accent, #6366f1);
        background: var(--sr-accent-weak, rgba(99, 102, 241, 0.12));
        color: var(--fg, #2a2d33);
        font: inherit;
        font-weight: 600;
        font-size: 0.82rem;
        padding: 0.3rem 0.7rem;
        border-radius: 999px;
        cursor: pointer;
    }
    .focus-chip:hover {
        background: var(--sr-accent, #6366f1);
        color: #fff;
    }

    /* Overall mastery */
    .overall {
        border: 1px solid var(--border, #e6e7eb);
        border-radius: 16px;
        padding: 1.25rem 1.4rem 1.35rem;
        margin: 0 0 1.25rem;
        background: var(--canvas-elevated, #fff);
        box-shadow: 0 2px 10px rgba(15, 23, 42, 0.05);
    }
    .overall-head {
        display: flex;
        align-items: baseline;
        justify-content: space-between;
        gap: 1rem;
    }
    .overall-head h2 {
        margin: 0;
        font-size: 1.15rem;
        font-weight: 700;
    }
    .overall-count {
        font-weight: 700;
        font-size: 0.95rem;
    }
    .stack {
        display: flex;
        height: 16px;
        margin: 0.8rem 0 0.6rem;
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
        border: 1px solid var(--border, #e6e7eb);
        border-radius: 16px;
        padding: 1.25rem 1.4rem 1.35rem;
        margin: 0 0 1.25rem;
        background: var(--canvas-elevated, #fff);
        box-shadow: 0 2px 10px rgba(15, 23, 42, 0.05);
    }
    .plan-head {
        display: flex;
        align-items: baseline;
        justify-content: space-between;
        gap: 1rem;
    }
    .plan-head h2 {
        margin: 0;
        font-size: 1.15rem;
        font-weight: 700;
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
    .plan-more {
        margin-top: 0.8rem;
        padding: 0.4rem 0.85rem;
        border: 1px dashed var(--border, #c7c7cc);
        border-radius: 7px;
        background: transparent;
        font: inherit;
        font-weight: 600;
        font-size: 0.82rem;
        cursor: pointer;
        color: var(--fg, #33373d);
    }
    .plan-more:hover {
        background: var(--canvas-inset, #f0f1f3);
    }

    /* Exam pace */
    .pace {
        border: 1px solid var(--border, #e6e7eb);
        border-radius: 16px;
        padding: 1.25rem 1.4rem 1.35rem;
        margin: 0 0 1.25rem;
        background: var(--canvas-elevated, #fff);
        box-shadow: 0 2px 10px rgba(15, 23, 42, 0.05);
    }
    .pace-head {
        display: flex;
        align-items: baseline;
        justify-content: space-between;
        gap: 1rem;
    }
    .pace-head h2 {
        margin: 0;
        font-size: 1.15rem;
        font-weight: 700;
    }
    .pace-badge {
        border-radius: 999px;
        padding: 0.15rem 0.6rem;
        font-size: 0.75rem;
        font-weight: 700;
        white-space: nowrap;
    }
    .pace-badge.ok {
        background: #57a37c22;
        color: #3f8a63;
    }
    .pace-badge.behind {
        background: #e0a55226;
        color: #b9791f;
    }
    .pace-badge.past {
        background: var(--canvas-inset, #ececef);
        color: var(--fg-subtle, #6b7280);
    }
    .pace-row {
        display: flex;
        align-items: flex-end;
        gap: 0.75rem;
        margin: 0.7rem 0 0;
    }
    .pace-date {
        display: flex;
        flex-direction: column;
        gap: 0.2rem;
        font-size: 0.78rem;
        color: var(--fg-subtle, #6b7280);
    }
    .pace-date input {
        font: inherit;
        padding: 0.3rem 0.4rem;
        border: 1px solid var(--border, #c7c7cc);
        border-radius: 6px;
        background: var(--canvas, #fff);
        color: inherit;
    }
    .pace-clear {
        padding: 0.35rem 0.7rem;
        border: 1px solid var(--border, #c7c7cc);
        border-radius: 6px;
        background: transparent;
        font: inherit;
        font-size: 0.8rem;
        cursor: pointer;
    }
    .pace-detail {
        margin: 0.7rem 0 0;
        font-size: 0.86rem;
        line-height: 1.5;
        color: var(--fg, #33373d);
    }
    .pace-fix {
        margin: 0.5rem 0 0;
        font-size: 0.86rem;
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 0.5rem;
        color: var(--fg-subtle, #4b5563);
    }
    .pace-raise {
        padding: 0.3rem 0.75rem;
        border: 1px solid #6486bf;
        border-radius: 7px;
        background: transparent;
        color: #6486bf;
        font: inherit;
        font-weight: 600;
        font-size: 0.82rem;
        cursor: pointer;
    }
    .pace-raise:hover {
        background: #6486bf14;
    }

    /* Concept map */
    .map-card {
        border: 1px solid var(--border, #e6e7eb);
        border-radius: 18px;
        padding: 0.5rem 0.75rem;
        background:
            radial-gradient(
                120% 120% at 50% 0%,
                var(--sr-accent-weak, rgba(99, 102, 241, 0.06)),
                transparent 60%
            ),
            var(--canvas-elevated, #fff);
        box-shadow: 0 2px 14px rgba(15, 23, 42, 0.06);
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

    /* Round bubbles (centre + units) */
    .bubble {
        position: absolute;
        box-sizing: border-box;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 2px;
        border: 3px solid var(--border, #e2e2e5);
        border-radius: 50%;
        padding: 6px;
        text-align: center;
        font: inherit;
        color: inherit;
        overflow: hidden;
        background:
            linear-gradient(var(--tint), var(--tint)), var(--canvas-elevated, #fbfbfc);
        box-shadow: 0 2px 8px rgba(15, 23, 42, 0.08);
    }
    .node-title {
        font-weight: 700;
        font-size: 0.92rem;
        line-height: 1.15;
    }
    .node-sub {
        font-size: 0.74rem;
        color: var(--fg-subtle, #6b7280);
    }
    .node-pct {
        font-size: 0.72rem;
        font-weight: 700;
        line-height: 1.15;
        color: var(--sr-accent, #6366f1);
    }
    .bubble.center {
        border-width: 3.5px;
        box-shadow:
            0 0 0 6px var(--sr-accent-weak, rgba(99, 102, 241, 0.1)),
            0 4px 14px rgba(15, 23, 42, 0.12);
    }
    .bubble.center .node-title {
        font-size: 1.2rem;
        font-weight: 800;
    }
    .bubble.unit {
        cursor: pointer;
        transition:
            box-shadow 0.12s ease,
            transform 0.12s ease;
    }
    .bubble.unit .node-title {
        font-size: 1rem;
    }
    .bubble.unit:hover {
        box-shadow:
            0 0 0 4px var(--tint),
            0 4px 12px rgba(15, 23, 42, 0.14);
        transform: translateY(-1px);
    }
    .bubble.unit.selected {
        box-shadow: 0 0 0 4px var(--fg-subtle, #6b7280);
    }

    /* Subtopic: a circular bubble with its label INSIDE it. */
    .leaf {
        position: absolute;
        box-sizing: border-box;
        display: flex;
        align-items: center;
        justify-content: center;
        text-align: center;
        padding: 5px;
        border: 3px solid var(--border, #e2e2e5);
        border-radius: 50%;
        background:
            linear-gradient(var(--tint), var(--tint)), var(--canvas-elevated, #fbfbfc);
        box-shadow: 0 2px 6px rgba(15, 23, 42, 0.07);
        font: inherit;
        color: inherit;
        cursor: pointer;
        overflow: hidden;
        transition:
            box-shadow 0.12s ease,
            transform 0.12s ease;
    }
    .leaf-label {
        font-size: 0.8rem;
        line-height: 1.2;
        font-weight: 600;
        overflow-wrap: break-word;
        hyphens: auto;
        color: var(--fg, #33373d);
    }
    .leaf:hover {
        box-shadow:
            0 0 0 4px var(--tint),
            0 4px 12px rgba(15, 23, 42, 0.14);
        transform: scale(1.06);
        z-index: 3;
    }
    .leaf.selected {
        box-shadow: 0 0 0 3px var(--fg-subtle, #6b7280);
        z-index: 3;
    }
    .leaf.selected .leaf-label {
        font-weight: 700;
    }
    /* Today's focus: a distinct accent glow that draws the eye. */
    .leaf.focus {
        box-shadow:
            0 0 0 4px var(--sr-accent-glow, rgba(99, 102, 241, 0.4)),
            0 2px 8px rgba(0, 0, 0, 0.12);
        animation: focusPulse 2.4s ease-in-out infinite;
    }
    @keyframes focusPulse {
        0%,
        100% {
            box-shadow:
                0 0 0 4px var(--sr-accent-glow, rgba(99, 102, 241, 0.4)),
                0 2px 8px rgba(0, 0, 0, 0.1);
        }
        50% {
            box-shadow:
                0 0 0 7px var(--sr-accent-weak, rgba(99, 102, 241, 0.12)),
                0 2px 10px rgba(0, 0, 0, 0.12);
        }
    }

    /* Locked subtopic: prerequisites not met yet (guided mode). */
    .leaf.locked {
        border-style: dashed;
        filter: grayscale(0.25);
        opacity: 0.82;
    }
    /* Dim bubbles outside the selected subtopic's prerequisite chain. */
    .leaf.dim {
        opacity: 0.3;
    }
    .lock-badge {
        position: absolute;
        top: 7px;
        left: 50%;
        transform: translateX(-50%);
        font-size: 0.72rem;
        line-height: 1;
    }

    /* detail */
    .detail {
        border: 1px solid var(--border, #e6e7eb);
        border-radius: 16px;
        padding: 1.25rem 1.4rem;
        margin-top: 1.25rem;
        background: var(--canvas-elevated, #fff);
    }
    /* Floating popup: appears immediately over the map on click, so it's obvious
       something opened (rather than a panel far down the page). */
    .detail-popup {
        position: fixed;
        top: 84px;
        right: 24px;
        width: 360px;
        max-width: calc(100vw - 48px);
        max-height: 78vh;
        overflow-y: auto;
        margin-top: 0;
        z-index: 60;
        box-shadow: 0 18px 48px rgba(15, 23, 42, 0.24);
        animation: popIn 0.12s ease;
    }
    @keyframes popIn {
        from {
            opacity: 0;
            transform: translateY(-6px);
        }
        to {
            opacity: 1;
            transform: none;
        }
    }
    .detail-close {
        position: absolute;
        top: 8px;
        right: 12px;
        border: none;
        background: transparent;
        font-size: 1.4rem;
        line-height: 1;
        cursor: pointer;
        color: var(--fg-subtle, #6b7280);
    }
    .detail-close:hover {
        color: var(--fg, #1c1c1e);
    }
    .detail-head {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 1rem;
    }
    .detail-head h2 {
        margin: 0;
        font-size: 1.2rem;
        font-weight: 700;
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

    /* Performance (practice tests): a SEPARATE panel from the memory-gate
       stats above, so the two signals never read as one blended number. */
    .perf {
        margin: 0.75rem 0 0;
        padding: 0.55rem 0.7rem;
        border: 1px solid var(--border-subtle, #e6e6ea);
        border-radius: 8px;
        background: var(--canvas-inset, #f4f5f7);
    }
    .perf-head {
        display: flex;
        align-items: baseline;
        justify-content: space-between;
        gap: 0.5rem;
    }
    .perf-title {
        font-weight: 700;
        font-size: 0.82rem;
    }
    .perf-sep {
        font-size: 0.68rem;
        color: var(--fg-subtle, #9ca3af);
    }
    .perf-body {
        margin-top: 0.3rem;
        font-size: 0.86rem;
    }
    .perf-body.pending {
        font-style: italic;
        color: var(--fg-subtle, #6b7280);
        font-size: 0.8rem;
    }

    /* Lock reason + per-topic bypass */
    .lock-note {
        margin: 0.75rem 0 0;
        padding: 0.6rem 0.7rem;
        border: 1px solid #e0a55255;
        background: #e0a55214;
        border-radius: 8px;
        font-size: 0.82rem;
        line-height: 1.45;
        color: var(--fg, #33373d);
    }
    .unlock-btn {
        display: inline-block;
        margin-top: 0.4rem;
        padding: 0.25rem 0.6rem;
        border: 1px solid #b9791f;
        border-radius: 6px;
        background: transparent;
        color: #b9791f;
        font: inherit;
        font-weight: 600;
        font-size: 0.8rem;
        cursor: pointer;
    }
    .unlock-btn:hover {
        background: #e0a55222;
    }
    .study-btn {
        margin-top: 1rem;
        width: 100%;
        padding: 0.7rem 0.9rem;
        border: none;
        border-radius: 11px;
        background: var(--sr-accent, #6366f1);
        color: #fff;
        font: inherit;
        font-weight: 700;
        font-size: 0.95rem;
        cursor: pointer;
        box-shadow: 0 2px 8px rgba(99, 102, 241, 0.28);
        transition:
            filter 0.12s ease,
            transform 0.12s ease;
    }
    .study-btn:hover {
        filter: brightness(1.06);
        transform: translateY(-1px);
    }
    .study-btn.secondary {
        margin-top: 0.6rem;
        background: transparent;
        color: var(--sr-accent, #6366f1);
        border: 1px solid var(--sr-accent, #6366f1);
        box-shadow: none;
    }
    /* Calm by default: honour reduced-motion preferences. */
    @media (prefers-reduced-motion: reduce) {
        .bubble.unit,
        .leaf {
            transition: none;
        }
        .leaf:hover {
            transform: none;
        }
        .leaf.focus {
            animation: none;
        }
    }
</style>
