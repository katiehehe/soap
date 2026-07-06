<!--
Copyright: Ankitects Pty Ltd and contributors
License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
-->
<script lang="ts">
    import { createEventDispatcher, onMount } from "svelte";
    import { slide } from "svelte/transition";

    import { bridgeCommand, bridgeCommandsAvailable } from "@tslib/bridgecommand";
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
        SubtopicMastery,
        UnitMastery,
    } from "@generated/anki/speedrun_pb";

    import type {
        LeafNode,
        PaceView,
        PerfEvidence,
        PrereqEdge,
        SubtopicEvidence,
        TestScope,
        UnitNode,
    } from "./lib";
    import {
        arrowHead,
        bubbleColor,
        COLORS,
        computeLayout,
        fillSegment,
        groupPlanByTier,
        hasEnoughEvidence,
        hierEdges,
        leafProgress,
        MIN_PROBLEMS,
        NODE_TOUCH,
        paceTone,
        perfColor,
        perfProgress,
        perfStatus,
        perfStatusLabel,
        prereqChain,
        prereqEdges,
        projectedFinishWeeks,
        rollupPerf,
        shrinkCircle,
        statusLabel,
        subtopicTag,
        TAXONOMY,
        UNIT_PREREQS,
    } from "./lib";
    import ReadinessBundle from "../readiness-dashboard/ReadinessBundle.svelte";

    const layout = computeLayout();
    const { center, units } = layout;
    const allTags = units.flatMap((u) => u.subs.map((s) => s.tag));
    // Directed prerequisite arrows, computed once from the fixed geometry. The
    // guided sequence is always shown (advisory recommended order, never a gate).
    // prereqEdges lands each arrowhead on the RENDERED squircle border, so the tip
    // touches the drawn bubble edge, no gap floating short of it, nothing under a
    // corner (matching the bubble-mask, which clips the rails at that same border).
    const prereqArrows = prereqEdges(layout);

    // The bubble-mask holes (which punch each bubble out of the track layer) are
    // squircles that EXACTLY match the rendered bubbles, so every connector shows
    // right up to the drawn border with nothing peeking through a rounded corner
    // and no gap that makes a node look detached. A bubble is `border-radius: 34%`
    // (of its 2r box) rendered at `scale(NODE_TOUCH)`, so its drawn corner radius
    // is 0.34·2·(NODE_TOUCH·r). MASK_RX is that corner radius as a fraction of the
    // hole half-width (NODE_TOUCH·r), i.e. 2 × 0.34. It MUST stay in sync with the
    // 34% border-radius on .bubble / .leaf below, or corners will gap or peek.
    const MASK_RX = 0.68; // = 2 × 0.34 (the .bubble / .leaf border-radius)

    // Practice = exam-style problems (the performance spine). A bubble's
    // "Practice" opens a scoped practice test; the home shell listens for this
    // event and swaps in the practice-test view, scoped to a subtopic, a unit,
    // or the whole exam (the centre bubble).
    const dispatch = createEventDispatcher<{ practicetest: TestScope }>();

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
    // 1-based unit number in syllabus order, so the map and cram labels read
    // "Unit 1/2/3" and the three units' order is unambiguous.
    const UNIT_NUMBER_BY_ID = new Map(TAXONOMY.map((u, i) => [u.id, i + 1]));

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
    const RED = COLORS.red;
    const MEMORY = COLORS.memory;
    const ACCENT = COLORS.accent;

    // Line STYLE is the primary way the two rails are told apart (so it works even
    // before either has any fill, and regardless of the performance colour):
    //   • Memory  = a SOLID line (continuous recall / spaced repetition).
    //   • Performance = a DOTTED line (discrete practice attempts).
    // Widely-spaced dots (round-capped) read unmistakably as "not solid" next to
    // the Memory rail. One source of truth for the dash pattern → the legend swatch
    // below draws the exact same dasharray, so it always matches the rendered line.
    const PERF_DASH = "1 9";
    // The legend's Performance swatch is a KEY, so it must ALWAYS render a clearly
    // visible dotted line, independent of live data. It uses one fixed,
    // representative performance colour (amber = "practising") drawn as a plain
    // solid stroke; a per-status colour or an objectBoundingBox gradient (whose
    // bounding box is degenerate on a horizontal line) can render nothing, which is
    // what left the swatch blank. The rails on the MAP still show each topic's real
    // traffic-light colour.
    const PERF_KEY_COLOR = AMBER;

    // Which sections to render. The home shell renders one slice per tab: the
    // bubble map (variant "map"), Today's plan + Mastery pace ("plan"), the memory
    // (spaced-repetition) view ("memory"), or the coverage statistics ("stats").
    // The standalone /study-map route shows everything ("full").
    export let variant: "map" | "plan" | "memory" | "cram" | "stats" | "full" = "full";
    // Whether the tiered mastery scheduler is ON. When OFF (the ablation), the
    // Today's-plan panel drops the tier grouping/labels and shows a flat list,
    // matching what the review queue actually serves (plain Anki order).
    export let masteryScheduler = true;
    $: showMap = variant === "map" || variant === "full";
    $: showPlan = variant === "plan" || variant === "full";
    $: showMemory = variant === "memory" || variant === "full";
    $: showStats = variant === "stats" || variant === "full";
    // The Cram tab shows ONLY the unlimited-practice controls (no memory score or
    // due summary) so it reads as "solely a cram tab"; the full/memory views keep
    // cram beneath the memory signal.
    $: showCram = variant === "cram" || variant === "memory" || variant === "full";

    let result: MasteryState | null = null;
    let readiness: ReadinessResult | null = null;
    let studyPlan: StudyPlan | null = null;
    let pace: StudyPace | null = null;
    let loadError = "";
    // Unseen new cards the daily limit is still holding back in the exam deck
    // (ignoring today's cap), fetched from the desktop bridge. `null` means
    // unknown (no bridge: the browser/e2e, or the phone before its native
    // handler exists), where we keep the "study more" lever as a safe fallback.
    // It makes that lever honest: raising today's new limit only surfaces cards
    // when some remain, so at 0 we say "caught up" instead of a button that
    // quietly does nothing (extend_limits has nothing to add).
    let newRemaining: number | null = null;
    let selectedLeaf: LeafNode | null = null;
    let selectedUnit: UnitNode | null = null;
    // The centre "Exam P" node opens an overall-mastery detail; mastery lives
    // here now (clicked from the map), not in the Stats tab (which is Anki-only).
    let selectedRoot = false;
    // Whether the readiness banner's "Evidence / how this is computed" section is
    // expanded, revealing the full honesty bundle in this same view.
    let evidenceOpen = false;

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
        // Desktop only: how many new cards the daily limit is still holding back,
        // so the "study more today" lever is honest (see newRemaining). Read-only
        // count; a plain browser / the phone (no bridge) leaves it null.
        if (bridgeCommandsAvailable()) {
            bridgeCommand<number>("speedrun-new-remaining", (n) => {
                newRemaining = typeof n === "number" ? n : null;
            });
        }
    }
    onMount(() => {
        loadState();
        // Bug fix: the counts were only fetched once at mount, so a subtopic's
        // "N due" count did not clear after finishing a review until a full
        // reload. Re-fetch whenever the page becomes visible again (returning
        // from a review session, a tab/app focus change, a WebView resume, or a
        // bfcache/back-forward restore) so the due counts refresh in place.
        // loadState() only reads state, so re-running is safe. Cross-platform;
        // also covers the desktop return-from-review case.
        function refetchIfVisible(): void {
            if (document.visibilityState === "visible") {
                loadState();
            }
        }
        document.addEventListener("visibilitychange", refetchIfVisible);
        // Some webviews restore from bfcache without firing visibilitychange;
        // pageshow covers that (and a persisted back/forward restore).
        window.addEventListener("pageshow", refetchIfVisible);
        return () => {
            document.removeEventListener("visibilitychange", refetchIfVisible);
            window.removeEventListener("pageshow", refetchIfVisible);
        };
    });

    $: subMap = new Map<string, SubtopicMastery>(
        (result?.subtopics ?? []).map((s) => [s.tag, s]),
    );
    $: unitMap = new Map<string, UnitMastery>(
        (result?.units ?? []).map((u) => [u.unitId, u]),
    );
    $: overall = result?.overall ?? null;
    $: priorities = result?.priorities ?? [];
    // Memory signal (FSRS retrievability, with a range) for the Memory tab.
    // Independent of the readiness give-up rule; blank (never guessed) until data.
    $: memoryRecall = readiness?.memoryRecall ?? null;
    // Today's plan: the decks with something due now, grouped by tier. Counts are
    // Anki's own daily-limit-capped numbers, so they match the deck list.
    $: planGroups = groupPlanByTier(studyPlan?.items ?? []);

    // Two independent, always-honest recommendations, drawn in DISTINCT hues so
    // they never blend (performance is the spine; memory is a support signal):
    //   • PRACTICE NEXT (performance): the highest exam-weight topic you're not
    //     yet strong at, where doing problems buys the most. Independent of memory.
    //   • REVIEW (memory): topics with spaced-repetition cards due now.
    // Both come from real data; nothing is fabricated.
    // Subtopics with cards actually due today (memory / spaced repetition).
    $: dueTodayTags = (() => {
        const tags = new Set<string>();
        for (const it of studyPlan?.items ?? []) {
            if (it.tier === StudyMode.BLOCKED && it.subtopicTag) {
                tags.add(it.subtopicTag);
            }
        }
        return tags;
    })();
    // Performance "practice next": highest exam weight × weakness among topics
    // not yet strong. Untested/thin topics count as fully weak (accuracy 0), so a
    // high-weight topic you've never practiced is itself a strong recommendation.
    $: practiceNextTag = ((_sm) => {
        let best = "";
        let bestScore = -1;
        for (const w of SUBTOPIC_WEIGHTS) {
            const perf = toPerf(subMap.get(w.tag));
            if (perfStatus(perf) === "strong") {
                continue;
            }
            const acc = perf && perf.perfQuestions > 0 ? perf.perfAccuracy : 0;
            const score = w.weight * (1 - acc);
            if (score > bestScore) {
                bestScore = score;
                best = w.tag;
            }
        }
        return best;
    })(subMap);
    // The single "practice next" recommendation shown in the focus strip: the one
    // highest-priority performance topic. The memory / review-due list that used
    // to sit beside it was removed as UI clutter; the memory signal still shows in
    // the readiness bundle and as the blue memory track on the map.
    $: practiceRec = practiceNextTag
        ? {
              tag: practiceNextTag,
              name: NAME_BY_TAG.get(practiceNextTag) ?? practiceNextTag,
          }
        : null;

    // Due-aware study routing. The plan is already tier-ordered (blocked →
    // within-unit → cross-unit) AND filtered to decks with cards due now, so its
    // first item is the honest "study next" target, one that always has cards.
    $: firstActionable = studyPlan?.items?.[0] ?? null;
    $: hasAnyDue = (studyPlan?.items?.length ?? 0) > 0;

    // Mastery pace (are you mastering the syllabus fast enough, not just seeing
    // it?). All values are measured counts / arithmetic, a mastery pace over
    // gate-cleared subtopics, never a score.
    $: paceView = pace
        ? ({
              hasExamDate: pace.hasExamDate,
              daysLeft: Number(pace.daysLeft),
              remainingSubtopics: pace.remainingSubtopics,
              masteredSubtopics: pace.masteredSubtopics,
              totalSubtopics: pace.totalSubtopics,
              daysStudied: pace.daysStudied,
              currentPerWeek: pace.currentPerWeek,
              recommendedPerWeek: pace.recommendedPerWeek,
              projectedDaysToFinish: pace.projectedDaysToFinish,
              onTrack: pace.onTrack,
          } satisfies PaceView)
        : null;
    $: paceState = paceView ? paceTone(paceView) : "none";
    // Noon-anchored timestamp -> the exam day is stable across time zones.
    $: examIso = paceView?.hasExamDate
        ? new Date(Number(pace!.examTimestamp) * 1000).toISOString().slice(0, 10)
        : "";

    // Readiness, surfaced at the top of the map to motivate the session. The
    // compact banner shows the score (with its range) when the engine emits one,
    // or the honest give-up state (reason + gates) when it withholds one, never a
    // fabricated number. The full honesty bundle sits behind the banner's
    // "Evidence" expander in this same view, so a score is never shown bare.
    $: noScore = readiness?.value.case === "noScore" ? readiness.value.value : null;
    $: readinessScore =
        readiness?.value.case === "score" ? readiness.value.value : null;
    // Distinguish the two honest abstain reasons the same way the readiness
    // dashboard does: held below the review/coverage gate, vs. the gate met but
    // awaiting graded practice-test evidence.
    $: readinessNeedsPractice =
        !!noScore && noScore.reason.toLowerCase().includes("practice");

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
    /** The subtopic's measured evidence, or null if we have none for it. */
    function ev(tag: string): SubtopicEvidence | null {
        return subMap.get(tag) ?? null;
    }

    /** Convert a subtopic's mastery row to its performance subset (or null). */
    function toPerf(m: SubtopicMastery | undefined): PerfEvidence | null {
        return m
            ? {
                  perfQuestions: m.perfQuestions,
                  perfCorrect: m.perfCorrect,
                  perfAccuracy: m.perfAccuracy,
                  performanceMastered: m.performanceMastered,
              }
            : null;
    }
    // Reactive bubble-colour maps. They read `subMap` directly, so bubbles and
    // edges re-colour the moment mastery state loads. PERFORMANCE first; a muted
    // MEMORY hint only when a topic is reviewed-but-not-practiced; grey if neither.
    $: leafColors = new Map<string, string>(
        units.flatMap((u) =>
            u.subs.map((s) => {
                const m = subMap.get(s.tag);
                return [s.tag, bubbleColor(toPerf(m), m?.reviews ?? 0)] as const;
            }),
        ),
    );
    // A unit's colour pools its subtopics' performance, so it reflects the whole
    // unit (memory the same secondary fallback).
    $: unitColors = new Map<string, string>(
        units.map((u) => {
            const rows = u.subs
                .map((s) => subMap.get(s.tag))
                .filter((m): m is SubtopicMastery => m !== undefined);
            const perfs = rows.map(toPerf).filter((p): p is PerfEvidence => p !== null);
            const reviews = rows.reduce((a, m) => a + (m.reviews ?? 0), 0);
            return [u.id, bubbleColor(rollupPerf(perfs), reviews)] as const;
        }),
    );

    // Performance evidence per subtopic (the practice track). Reactive off
    // subMap so the tracks re-fill the moment mastery state loads.
    $: leafPerf = new Map<string, PerfEvidence | null>(
        units.flatMap((u) =>
            u.subs.map((s) => [s.tag, toPerf(subMap.get(s.tag))] as const),
        ),
    );
    // Memory (spaced-repetition) fill per subtopic, the existing honest gate
    // progress. A separate map so the two tracks never share one value. Read
    // `subMap` DIRECTLY here (not through the ev() helper): a Svelte reactive
    // statement only re-runs when a variable it NAMES changes, and it cannot see
    // the subMap read hidden inside ev(). Routing through ev() froze this map at
    // its first (empty subMap, so leafProgress -> 0) value and never refilled it
    // once mastery loaded, which left every Memory rail stuck at 0 while the
    // Performance rails (which read subMap directly, below) filled correctly.
    $: leafMemProgress = new Map<string, number>(
        units.flatMap((u) =>
            u.subs.map(
                (s) => [s.tag, leafProgress(subMap.get(s.tag) ?? null)] as const,
            ),
        ),
    );
    // Unit rollups: pooled performance (uncapped by time, it accrues from
    // practice regardless of the schedule) and the mean memory fill across the
    // unit's subtopics, so the centre→unit tracks each fill up gradually.
    $: unitPerf = new Map<string, PerfEvidence>(
        units.map((u) => {
            const perfs = u.subs
                .map((s) => leafPerf.get(s.tag) ?? null)
                .filter((p): p is PerfEvidence => p !== null);
            return [u.id, rollupPerf(perfs)] as const;
        }),
    );
    $: unitMemProgress = new Map<string, number>(
        units.map((u) => {
            const vals = u.subs.map((s) => leafMemProgress.get(s.tag) ?? 0);
            const mean = vals.length
                ? vals.reduce((a, b) => a + b, 0) / vals.length
                : 0;
            return [u.id, mean] as const;
        }),
    );

    // One drawn rail: a single metric's line between two bubbles. Every link
    // draws TWO (a Memory track and a Performance track) because there are two
    // independent signals; they must never blend into one line.
    interface Track {
        x1: number;
        y1: number;
        x2: number;
        y2: number;
        progress: number;
        color: string;
        kind: "memory" | "performance";
    }

    // Aim each rail at the VISIBLE bubble border (NODE_TOUCH·r), not the full
    // collision radius r. Bubbles render at scale(0.88) (a squircle inset so
    // neighbours never touch), so a rail drawn to r stops in the empty ring
    // between the drawn bubble and its collision circle and reads as "floating".
    // The SAME NODE_TOUCH drives the bubble-mask below, so the mask hole matches
    // the drawn bubble and the rails emerge exactly at its edge. hierEdges then
    // returns two parallel border-to-border rails, offset ± so Memory and
    // Performance sit side by side and both still touch the bubbles.
    const shrink = (c: { x: number; y: number; r: number }) =>
        shrinkCircle(c, NODE_TOUCH);

    // Two rails per link, oriented CHILD → PARENT so the fill flows UP the
    // hierarchy: subtopic → unit, then unit → the central "Exam P" node. Each
    // rail's (x1,y1) sits on the CHILD's border, so the coloured fill grows out
    // from the child (its mastery feeding the parent). Memory (solid periwinkle,
    // fill = the child's memory progress) and Performance (dotted traffic-light,
    // fill = the child's performance progress) each fill 0→1 on ITS OWN metric,
    // never blended.
    $: tracks = [
        // topic → exam: the unit is the child, the centre ("Exam P") the parent.
        ...units.flatMap((u): Track[] => {
            const two = hierEdges(shrink(u), shrink(center));
            const perf = unitPerf.get(u.id) ?? null;
            return [
                {
                    ...two.memory,
                    progress: unitMemProgress.get(u.id) ?? 0,
                    color: MEMORY,
                    kind: "memory",
                },
                {
                    ...two.performance,
                    progress: perfProgress(perf),
                    color: perfColor(perf),
                    kind: "performance",
                },
            ];
        }),
        // subtopic → topic: the subtopic is the child, its unit the parent.
        ...units.flatMap((u): Track[] =>
            u.subs.flatMap((s): Track[] => {
                const two = hierEdges(shrink(s), shrink(u));
                const perf = leafPerf.get(s.tag) ?? null;
                return [
                    {
                        ...two.memory,
                        progress: leafMemProgress.get(s.tag) ?? 0,
                        color: MEMORY,
                        kind: "memory",
                    },
                    {
                        ...two.performance,
                        progress: perfProgress(perf),
                        color: perfColor(perf),
                        kind: "performance",
                    },
                ];
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
        selectedRoot = false;
    }
    function selectUnit(node: UnitNode): void {
        selectedUnit = node;
        selectedLeaf = null;
        selectedRoot = false;
    }
    function selectRoot(): void {
        selectedRoot = true;
        selectedLeaf = null;
        selectedUnit = null;
    }
    function closeDetail(): void {
        selectedLeaf = null;
        selectedUnit = null;
        selectedRoot = false;
    }
    // Review (MEMORY), unlimited cram: a no-reschedule cram deck on the desktop,
    // so you can drill flashcards from a subtopic / unit / everything any time
    // without touching the FSRS schedule or the daily limits. Memory is the
    // SUPPORT track; performance (the practice tests below) is the spine.
    function cramSubtopic(tag: string): void {
        bridgeCommand("speedrun-practice:" + tag);
    }
    function cramUnit(unitId: string): void {
        bridgeCommand("speedrun-practice-unit:" + unitId);
    }
    function cramAll(): void {
        bridgeCommand("speedrun-practice-all");
    }
    // Practice (PERFORMANCE, the spine): open a scoped exam-style practice test.
    // Practicing a unit interleaves its subtopics and records per-subtopic
    // performance, so it lifts the performance of every subtopic it touches.
    function practiceTopic(tag: string): void {
        dispatch("practicetest", { kind: "subtopic", tag });
    }
    function practiceUnitTest(unitId: string): void {
        dispatch("practicetest", { kind: "unit", id: unitId });
    }
    function practiceAllTest(): void {
        dispatch("practicetest", { kind: "all" });
    }
    // "Study next" label taken from the first actionable plan item, so the label,
    // the destination, and "has cards due" are always the same thing.
    function planTierLabel(it: StudyPlanItem): string {
        if (it.tier === StudyMode.BLOCKED) {
            return `Study next: blocked practice · ${NAME_BY_TAG.get(it.subtopicTag) ?? it.deckName}`;
        }
        if (it.tier === StudyMode.WITHIN_UNIT) {
            return `Study next: within-unit interleaving · ${UNIT_NAME_BY_ID.get(it.unitId) ?? it.deckName}`;
        }
        if (it.tier === StudyMode.CROSS_UNIT) {
            return "Study next: cross-unit review";
        }
        return "Study next";
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
    function studyMore(): void {
        // "Go ahead" beyond today's quota: extend today's new limit and study.
        bridgeCommand("speedrun-extend-new:20");
    }
    // --- prerequisite-arrow highlight (advisory guided sequence, never a gate) ---
    function arrowActive(e: PrereqEdge): boolean {
        return !!selectedLeaf && highlightSet.has(e.from) && highlightSet.has(e.to);
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
        // The arrowHEAD is the connection point: keep it solid enough (even at
        // rest) that its tip visibly meets the bubble border, so the arrow never
        // reads as "floating" even though its thin tip already lands on the border.
        return active ? 0.95 : 0.66;
    }
</script>

<div class="study-map" class:cram-view={variant === "cram"}>
    {#if showMap}
        <header>
            <h1>Study map</h1>
            <p class="exam">SOA Exam P · Probability</p>
        </header>
    {/if}

    {#if loadError}
        <div class="notice error">Couldn't load mastery: {loadError}</div>
    {/if}

    {#if showMap && (readiness || practiceRec)}
        <div class="top-row">
            {#if readiness}
                <section
                    class="readiness-banner"
                    class:has-score={readinessScore}
                    aria-label="Exam readiness"
                >
                    {#if readinessScore}
                        <div class="rb-top">
                            <div class="rb-headline">
                                <span class="rb-kicker">
                                    Readiness · would you pass today?
                                </span>
                                <div class="rb-score">
                                    <span class="rb-point">
                                        {readinessScore.point.toFixed(1)}
                                    </span>
                                    <span class="rb-outof">/ 10</span>
                                    <span class="rb-range">
                                        ({readinessScore.low.toFixed(
                                            1,
                                        )}-{readinessScore.high.toFixed(1)})
                                    </span>
                                </div>
                                <div class="rb-facts">
                                    <span>
                                        P(pass) <b>
                                            {pct(readinessScore.passProbability)}
                                        </b>
                                    </span>
                                    <span class="rb-dot" aria-hidden="true">·</span>
                                    <span>
                                        Coverage <b>
                                            {pct(readinessScore.coveragePct)}
                                        </b>
                                    </span>
                                    <span class="rb-dot" aria-hidden="true">·</span>
                                    <span>
                                        Confidence <b>
                                            {pct(readinessScore.confidence)}
                                        </b>
                                    </span>
                                </div>
                            </div>
                        </div>
                    {:else if noScore}
                        <div class="rb-top">
                            <div class="rb-headline">
                                <span class="rb-kicker abstain">
                                    Readiness · not enough data yet
                                </span>
                                <p class="rb-reason">{noScore.reason}</p>
                                <div class="rb-gates">
                                    <span class="rb-gate">
                                        <span class="rb-gate-label">
                                            Graded reviews
                                        </span>
                                        <b>{noScore.gradedReviews} / 200</b>
                                    </span>
                                    <span class="rb-gate">
                                        <span class="rb-gate-label">
                                            Syllabus practiced
                                        </span>
                                        <b>{pct(noScore.coveragePct)}</b>
                                        <span class="rb-gate-need">need ≥ 50%</span>
                                    </span>
                                    <span class="rb-gate">
                                        <span class="rb-gate-label">
                                            Graded practice tests
                                        </span>
                                        <b>
                                            {readinessNeedsPractice
                                                ? "needed now"
                                                : "after the gates above"}
                                        </b>
                                    </span>
                                </div>
                            </div>
                        </div>
                    {/if}

                    <div class="rb-evidence">
                        <button
                            type="button"
                            class="rb-toggle"
                            aria-expanded={evidenceOpen}
                            on:click={() => (evidenceOpen = !evidenceOpen)}
                        >
                            <span>
                                {evidenceOpen
                                    ? "Hide evidence"
                                    : "Evidence / how this is computed"}
                            </span>
                            <span
                                class="rb-chevron"
                                class:open={evidenceOpen}
                                aria-hidden="true"
                            >
                                ▾
                            </span>
                        </button>
                        {#if evidenceOpen}
                            <div class="rb-bundle" transition:slide>
                                <ReadinessBundle result={readiness} />
                            </div>
                        {/if}
                    </div>
                </section>
            {/if}

            {#if practiceRec}
                {@const pr = practiceRec}
                <section class="focus-strip" aria-label="What to do next">
                    <div class="rec-stack">
                        <!-- Performance / practice: one big amber call-to-action. It
                             doubles as readiness's single best next action (the engine
                             names the same topic). The memory / review-due list that
                             used to sit below was removed as UI clutter; memory still
                             shows in the readiness bundle and the map's memory track. -->
                        <div class="rec rec-perf">
                            <span class="rec-mark perf" aria-hidden="true">
                                <svg
                                    viewBox="0 0 24 24"
                                    fill="none"
                                    stroke="currentColor"
                                    stroke-width="2.4"
                                    stroke-linecap="round"
                                    stroke-linejoin="round"
                                >
                                    <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" />
                                    <polyline points="17 6 23 6 23 12" />
                                </svg>
                            </span>
                            <div class="rec-main">
                                <span class="rec-kicker perf">
                                    Practice next
                                    <span class="rec-axis">performance</span>
                                </span>
                                <button
                                    class="rec-cta"
                                    title="Practice next: do exam-style problems here to raise your performance"
                                    on:click={() => practiceTopic(pr.tag)}
                                >
                                    <span class="rec-topic">{pr.name}</span>
                                </button>
                            </div>
                        </div>
                    </div>
                </section>
            {/if}
        </div>
    {/if}

    {#if showPlan && studyPlan}
        <section class="plan" aria-label="Today's study plan">
            <div class="plan-head">
                <h2>Today's plan</h2>
            </div>
            {#if hasAnyDue && firstActionable}
                {@const fa = firstActionable}
                <button
                    class="study-btn"
                    on:click={() => studyDeck(fa.deckId)}
                    title="Open the single highest-priority deck that has cards due now"
                >
                    {masteryScheduler
                        ? planTierLabel(fa)
                        : `Study next: ${planLabel(fa)}`}
                </button>
            {:else}
                <button
                    class="study-btn"
                    disabled
                    title="Nothing due right now, you're caught up"
                >
                    Caught up, nothing due today
                </button>
            {/if}
            {#if planGroups.length === 0}
                <!-- "Study more" is a beyond-the-quota lever, shown once today's
                     due cards are cleared. It only does something when the daily
                     limit is still holding back unseen new cards; once every new
                     card has been introduced (newRemaining === 0) raising the
                     limit surfaces nothing, so show the honest caught-up note
                     rather than a button that quietly does nothing. newRemaining
                     === null (no desktop bridge, e.g. browser/e2e) keeps the
                     lever as a fallback so nothing regresses off-desktop. -->
                {#if newRemaining === 0}
                    <p class="plan-note plan-caught-up">
                        You've introduced every new card. Reviews return here as they
                        come due; practice any topic anytime below.
                    </p>
                {:else}
                    <button
                        class="plan-more"
                        on:click={studyMore}
                        title="Raise today's new-card limit by 20 and study them now"
                    >
                        Study more today (+20)
                    </button>
                {/if}
            {:else if masteryScheduler}
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
                    Counts are today's cards after Anki's daily limits, the same numbers
                    as the deck list. Blocked rows show a subtopic's own cards; higher
                    tiers unlock as you clear gates.
                </p>
            {:else}
                <!-- Scheduler OFF (ablation): plain review order, no tier grouping. -->
                {#each planGroups.flatMap((g) => g.items) as it}
                    <div class="plan-row">
                        <span class="plan-label">{planLabel(it)}</span>
                        <span class="plan-count">{planCounts(it)}</span>
                        <button
                            class="plan-study"
                            style="border-color: var(--sr-accent); color: var(--sr-accent);"
                            on:click={() => studyDeck(it.deckId)}
                        >
                            Study
                        </button>
                    </div>
                {/each}
            {/if}
        </section>
    {/if}

    {#if showPlan && pace}
        <section class="pace" aria-label="Mastery pace">
            <div class="pace-head">
                <h2>Mastery pace</h2>
                {#if paceState === "ok"}
                    <span class="pace-badge ok">On track</span>
                {:else if paceState === "behind"}
                    <span class="pace-badge behind">Behind</span>
                {:else if paceState === "gathering"}
                    <span class="pace-badge gathering">Gathering data</span>
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
                        Your exam date has passed; set a new one to track pace.
                    </p>
                {:else if paceView.remainingSubtopics === 0}
                    <p class="pace-detail">
                        You've mastered all
                        <b>{paceView.totalSubtopics}</b>
                        subtopics. Keep them warm with reviews and practice tests.
                    </p>
                {:else if paceState === "gathering"}
                    <p class="pace-detail">
                        You've mastered
                        <b>{paceView.masteredSubtopics}</b>
                        of
                        <b>{paceView.totalSubtopics}</b>
                        subtopics ·
                        <b>{paceView.daysLeft}</b>
                        days left.
                    </p>
                    <p class="pace-fix">
                        To be ready in time you'd need to master about
                        <b>{paceView.recommendedPerWeek.toFixed(1)}/week</b>
                        .
                    </p>
                {:else}
                    {@const projWeeks = projectedFinishWeeks(
                        paceView.projectedDaysToFinish,
                    )}
                    <p class="pace-detail">
                        You've mastered
                        <b>{paceView.masteredSubtopics}</b>
                        of
                        <b>{paceView.totalSubtopics}</b>
                        subtopics ·
                        <b>{paceView.daysLeft}</b>
                        days left · at your current
                        <b>{paceView.currentPerWeek.toFixed(1)}/week</b>
                        you'll master the rest in about
                        <b>{projWeeks}</b>
                        {projWeeks === 1 ? "week" : "weeks"}.
                    </p>
                    {#if !paceView.onTrack}
                        <p class="pace-fix">
                            To be ready in time, aim for about
                            <b>{paceView.recommendedPerWeek.toFixed(1)}/week</b>
                            , focus your weakest topics next.
                        </p>
                    {/if}
                {/if}
            {:else}
                <p class="pace-detail">
                    You've mastered
                    <b>{paceView?.masteredSubtopics ?? 0}</b>
                    of
                    <b>{paceView?.totalSubtopics ?? 0}</b>
                    subtopics so far. Set your exam date to see if you're mastering them fast
                    enough. This is a
                    <b>mastery pace</b>
                    , not a predicted score.
                </p>
            {/if}
        </section>
    {/if}

    {#if showMemory}
        <section class="memory" aria-label="Memory (spaced repetition)">
            <div class="memory-head">
                <h2>Memory</h2>
            </div>

            {#if memoryRecall?.hasData}
                <div class="memory-band">
                    <span class="memory-point">{pct(memoryRecall.point)}</span>
                    <span class="memory-range">
                        {pct(memoryRecall.low)}-{pct(memoryRecall.high)}
                    </span>
                </div>
                <p class="memory-detail">
                    {memoryRecall.reviewedCards} cards reviewed · 10th-90th percentile range
                    · source: FSRS retrievability
                </p>
            {:else}
                <div class="memory-band">
                    <span class="memory-point muted">Not yet scored</span>
                </div>
                <p class="memory-detail">
                    Review some cards first: the memory signal stays blank until there
                    is data (source: FSRS retrievability). Never guessed.
                </p>
            {/if}

            <p class="memory-due">
                {#if dueTodayTags.size > 0}
                    <b>{dueTodayTags.size}</b>
                    {dueTodayTags.size === 1 ? "subtopic has" : "subtopics have"}
                    spaced-repetition cards due now.
                {:else}
                    No spaced-repetition cards due right now, you're caught up.
                {/if}
            </p>

            {#if hasAnyDue && firstActionable}
                {@const fa = firstActionable}
                <button class="study-btn" on:click={() => studyDeck(fa.deckId)}>
                    Review due now
                </button>
            {:else}
                <button
                    class="study-btn"
                    disabled
                    title="Nothing due right now, you're caught up"
                >
                    No reviews due, caught up
                </button>
            {/if}
        </section>
    {/if}

    {#if showCram}
        <section class="memory" aria-label="Cram (unlimited practice)">
            <div class="memory-head">
                <h2>Cram</h2>
            </div>

            <button
                class="study-btn secondary"
                on:click={cramAll}
                title="Unlimited flashcard cram of the whole exam, never touches your spaced-repetition schedule or daily limits."
            >
                Review everything
            </button>

            <div class="memory-units">
                <span class="memory-units-label">Cram one unit</span>
                {#each units as u}
                    <button
                        class="memory-unit"
                        on:click={() => cramUnit(u.id)}
                        title="Unlimited cram of {u.name}, never touches the FSRS schedule or daily limits."
                    >
                        Unit {UNIT_NUMBER_BY_ID.get(u.id)}: {u.name}
                    </button>
                {/each}
            </div>
        </section>
    {/if}

    {#if showStats && overall}
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
                    ({priorities[0].reason})
                </p>
            {/if}
            <p class="overall-note">
                This is <b>demonstrated mastery</b>
                : only subtopics you've proven with real reviews (≥ {MIN_PROBLEMS} problems,
                ≥ 80% accurate, ≥ 90% retained) count. It is
                <b>not</b>
                a predicted exam score.
                {#if noScore}
                    Your projected score stays hidden until the give-up threshold is met
                    ({noScore.gradedReviews} / 200 graded reviews, {pct(
                        noScore.coveragePct,
                    )} of the syllabus practiced). Open the
                    <b>Readiness</b>
                    tab for the full breakdown.
                {:else}
                    Open the <b>Readiness</b>
                    tab for your projected score.
                {/if}
            </p>
        </section>
    {/if}

    {#if showMap}
        <div class="map-row">
            <div class="map-card">
                <div
                    class="track-legend"
                    aria-label="What the two lines between topics mean"
                >
                    <span class="track-key">
                        <svg
                            class="track-swatch"
                            width="30"
                            height="10"
                            viewBox="0 0 30 10"
                            aria-hidden="true"
                        >
                            <line
                                x1="2"
                                y1="5"
                                x2="28"
                                y2="5"
                                stroke={MEMORY}
                                stroke-width="3.5"
                                stroke-linecap="round"
                            />
                        </svg>
                        <span>
                            <b>Memory</b>
                            : recall
                        </span>
                    </span>
                    <span class="track-key">
                        <svg
                            class="track-swatch"
                            width="30"
                            height="10"
                            viewBox="0 0 30 10"
                            aria-hidden="true"
                        >
                            <line
                                x1="2"
                                y1="5"
                                x2="28"
                                y2="5"
                                stroke={PERF_KEY_COLOR}
                                stroke-width="4.5"
                                stroke-linecap="round"
                                stroke-dasharray={PERF_DASH}
                            />
                        </svg>
                        <span>
                            <b>Performance</b>
                            : problem-solving
                        </span>
                    </span>
                    <span class="track-hint">
                        Each line fills up the tree: subtopic → unit → Exam P.
                    </span>
                </div>
                <div class="map-key" aria-label="Bubble colour key">
                    <span class="map-key-item">
                        <span class="map-key-dot" style="color:{RED}">●</span>
                        struggling
                    </span>
                    <span class="map-key-item">
                        <span class="map-key-dot" style="color:{AMBER}">●</span>
                        practicing
                    </span>
                    <span class="map-key-item">
                        <span class="map-key-dot" style="color:{GREEN}">●</span>
                        strong
                    </span>
                    <span class="map-key-item">
                        <span class="map-key-dot" style="color:{GREY}">●</span>
                        not practiced
                    </span>
                    <span class="map-key-item">
                        <span class="map-key-dot" style="color:{MEMORY}">●</span>
                        reviewed but not yet practiced
                    </span>
                </div>
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
                            <!-- Punch every bubble out of the line layer so no
                            track or arrow is ever drawn UNDER a block: a line that
                            would cross a bubble stops exactly at its border and
                            resumes on the far side. Each hole is the SQUIRCLE the
                            bubble is actually drawn as: same centre, same
                            half-width (NODE_TOUCH·r) and the SAME corner radius
                            (MASK_RX·NODE_TOUCH·r) as its 34% border-radius, so the
                            connector meets the border with no dotted line peeking
                            through a rounded corner and no detached gap. -->
                            <defs>
                                <mask
                                    id="sr-bubble-mask"
                                    maskUnits="userSpaceOnUse"
                                    x="0"
                                    y="0"
                                    width={layout.width}
                                    height={layout.height}
                                >
                                    <rect
                                        x="0"
                                        y="0"
                                        width={layout.width}
                                        height={layout.height}
                                        fill="white"
                                    />
                                    <rect
                                        x={center.x - center.r * NODE_TOUCH}
                                        y={center.y - center.r * NODE_TOUCH}
                                        width={center.r * NODE_TOUCH * 2}
                                        height={center.r * NODE_TOUCH * 2}
                                        rx={center.r * NODE_TOUCH * MASK_RX}
                                        ry={center.r * NODE_TOUCH * MASK_RX}
                                        fill="black"
                                    />
                                    {#each units as u}
                                        <rect
                                            x={u.x - u.r * NODE_TOUCH}
                                            y={u.y - u.r * NODE_TOUCH}
                                            width={u.r * NODE_TOUCH * 2}
                                            height={u.r * NODE_TOUCH * 2}
                                            rx={u.r * NODE_TOUCH * MASK_RX}
                                            ry={u.r * NODE_TOUCH * MASK_RX}
                                            fill="black"
                                        />
                                        {#each u.subs as s}
                                            <rect
                                                x={s.x - s.r * NODE_TOUCH}
                                                y={s.y - s.r * NODE_TOUCH}
                                                width={s.r * NODE_TOUCH * 2}
                                                height={s.r * NODE_TOUCH * 2}
                                                rx={s.r * NODE_TOUCH * MASK_RX}
                                                ry={s.r * NODE_TOUCH * MASK_RX}
                                                fill="black"
                                            />
                                        {/each}
                                    {/each}
                                </mask>
                            </defs>
                            <g mask="url(#sr-bubble-mask)">
                                <!-- Two rails per link, offset so they never overlap.
                            They are told apart four ways at once so the pair is
                            unmistakable and clustered edges stay legible:
                              • Memory  = THIN SOLID periwinkle (support signal).
                              • Performance = BOLD DOTTED traffic-light (the spine).
                            Each rail rides a faint "lane" tinted to ITS OWN track
                            (periwinkle vs neutral) at low opacity, so bundles of
                            edges near a node don't smear into one grey mass; the
                            coloured fill grows from the CHILD end UP toward the
                            parent, 0→1 on THAT metric; the signals never blend. -->
                                {#each tracks as t}
                                    {@const isMem = t.kind === "memory"}
                                    {@const dash = isMem ? null : PERF_DASH}
                                    <!-- The empty "lane" is ALWAYS drawn (even at zero
                                evidence) so the student can see where each track
                                runs; the coloured fill above only grows with real
                                data. Dotted lines lay down far less ink than a solid
                                one, so the Performance lane gets a touch more opacity
                                to read as clearly as the Memory lane. -->
                                    {@const baseOpacity = isMem ? 0.4 : 0.55}
                                    <line
                                        x1={t.x1}
                                        y1={t.y1}
                                        x2={t.x2}
                                        y2={t.y2}
                                        stroke={isMem ? MEMORY : GREY}
                                        stroke-width={isMem ? 2 : 2.4}
                                        stroke-linecap="round"
                                        stroke-dasharray={dash}
                                        opacity={baseOpacity}
                                    />
                                    {#if t.progress > 0}
                                        {@const f = fillSegment(t, t.progress)}
                                        <line
                                            x1={f.x1}
                                            y1={f.y1}
                                            x2={f.x2}
                                            y2={f.y2}
                                            stroke={t.color}
                                            stroke-width={isMem ? 3.5 : 4.2}
                                            stroke-linecap="round"
                                            stroke-dasharray={dash}
                                        />
                                    {/if}
                                {/each}
                            </g>

                            <!-- directed prerequisite arrows: the advisory guided
                            sequence, always shown, never a gate.
                            Drawn OUTSIDE the bubble-mask: the solid arrowHEAD is a
                            filled triangle whose tip already lands exactly on the
                            rendered border (squircleBorderPoint), so it must NOT be
                            clipped by the node hole (that clip is what made the head
                            float short of the bubble). The tip sits on the border and
                            the head recedes back toward the source, so it touches the
                            bubble with no gap and never sits under it. -->
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
                                    points={arrowHead(
                                        a.geom,
                                        a.kind === "unit" ? 14 : 11,
                                    )}
                                    fill={arrowColor(active)}
                                    opacity={arrowFillOpacity(dim, active)}
                                />
                            {/each}
                        </svg>

                        <!-- centre: opens the overall-mastery detail (with a
                             whole-exam practice-test button inside it) -->
                        <button
                            type="button"
                            class="bubble center"
                            class:selected={selectedRoot}
                            style="left:{center.x - center.r}px; top:{center.y -
                                center.r}px;
                       width:{center.r * 2}px; height:{center.r * 2}px;
                       border-color:{ACCENT}; --tint:{ACCENT}1f;"
                            title="See your overall mastery across the whole exam, and take a practice test"
                            on:click={selectRoot}
                        >
                            <span class="node-title">Exam P</span>
                            {#if overall}
                                <span class="node-sub">
                                    {overall.subtopicsMastered}/{overall.subtopicsTotal}
                                </span>
                            {/if}
                            <span class="center-cta">Mastery</span>
                        </button>

                        <!-- units -->
                        {#each units as u}
                            {@const uc = unitColors.get(u.id) ?? GREY}
                            <button
                                class="bubble unit"
                                class:selected={selectedUnit?.id === u.id}
                                style="left:{u.x - u.r}px; top:{u.y - u.r}px;
                           width:{u.r * 2}px; height:{u.r * 2}px;
                           border-color:{uc}; --tint:{uc}1f;"
                                on:click={() => selectUnit(u)}
                            >
                                <span class="node-title">
                                    Unit {UNIT_NUMBER_BY_ID.get(u.id)}: {u.name}
                                </span>
                                <span class="node-pct">
                                    {Math.round(u.weight)}% of exam
                                </span>
                                <span class="node-sub">
                                    {unitMap.get(u.id)?.subtopicsCleared ?? 0}/{u.subs
                                        .length} mastered
                                </span>
                            </button>
                        {/each}

                        <!-- subtopics: bubble sized by weight, name label beneath -->
                        {#each units as u}
                            {#each u.subs as s}
                                {@const c = leafColors.get(s.tag) ?? GREY}
                                <button
                                    class="leaf"
                                    class:selected={selectedLeaf?.tag === s.tag}
                                    class:dim={selectedLeaf && !highlightSet.has(s.tag)}
                                    class:rec-next={practiceNextTag === s.tag &&
                                        !dueTodayTags.has(s.tag)}
                                    style="left:{s.x - s.r}px; top:{s.y - s.r}px;
                               width:{s.r * 2}px; height:{s.r * 2}px;
                               border-color:{c}; --tint:{c}1a;"
                                    title="{s.name} · exam weight {s.weight.toFixed(1)}"
                                    on:click={() => selectLeaf(s)}
                                >
                                    <span class="leaf-label">{s.name}</span>
                                    {#if practiceNextTag === s.tag && !dueTodayTags.has(s.tag)}
                                        <span
                                            class="rec-badge"
                                            aria-label="practice next"
                                        >
                                            next
                                        </span>
                                    {/if}
                                </button>
                            {/each}
                        {/each}
                    </div>
                </div>
            </div>
            {#if selectedRoot || selectedUnit || selectedLeaf}
                <section class="detail">
                    <button
                        class="detail-close"
                        on:click={closeDetail}
                        aria-label="Close detail"
                    >
                        ×
                    </button>
                    {#if selectedRoot}
                        <div class="detail-head">
                            <div>
                                <h2>SOA Exam P</h2>
                            </div>
                            {#if overall}
                                <span
                                    class="pill"
                                    style="background:{ACCENT}22; color:{ACCENT};"
                                >
                                    {overall.subtopicsMastered}/{overall.subtopicsTotal}
                                    mastered
                                </span>
                            {/if}
                        </div>
                        {#if overall}
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
                            <dl class="stats">
                                <div>
                                    <dt>Subtopics mastered</dt>
                                    <dd>
                                        {overall.subtopicsMastered} / {overall.subtopicsTotal}
                                    </dd>
                                </div>
                                <div>
                                    <dt>Units mastered</dt>
                                    <dd>
                                        {overall.unitsMastered} / {overall.unitsTotal}
                                    </dd>
                                </div>
                                <div>
                                    <dt>Mastery by weight</dt>
                                    <dd>{pct(overall.weightedMasteryPct)}</dd>
                                </div>
                                <div>
                                    <dt>In progress</dt>
                                    <dd>{overall.subtopicsInProgress}</dd>
                                </div>
                            </dl>
                            {#if priorities.length > 0}
                                <p class="hint">
                                    Weakest:
                                    <b>
                                        {NAME_BY_TAG.get(priorities[0].tag) ??
                                            priorities[0].subtopicId}
                                    </b>
                                    ({priorities[0].reason})
                                </p>
                            {/if}
                            <p class="hint">
                                Demonstrated mastery: only subtopics you've proven with
                                real reviews count. Never a predicted score.
                            </p>
                        {:else}
                            <p class="hint">
                                No mastery data yet. Review some cards first.
                            </p>
                        {/if}
                        <button
                            class="study-btn"
                            on:click={practiceAllTest}
                            title="Take a practice test: exam-shaped questions across the whole exam that build your Performance & Readiness signals"
                        >
                            Practice test
                        </button>
                        <button
                            class="study-btn secondary"
                            on:click={cramAll}
                            title="Unlimited flashcard cram of the whole exam, never touches your spaced-repetition schedule or daily limits."
                        >
                            Review everything
                        </button>
                    {:else if selectedUnit}
                        {@const um = unitMap.get(selectedUnit.id)}
                        {@const uc = unitColors.get(selectedUnit.id) ?? GREY}
                        {@const unitId = selectedUnit.id}
                        <div class="detail-head">
                            <div>
                                <h2>{selectedUnit.name}</h2>
                            </div>
                            <span class="pill" style="background:{uc}22; color:{uc};">
                                {um?.subtopicsCleared ?? 0}/{um?.subtopicsTotal ??
                                    selectedUnit.subs.length} mastered
                            </span>
                        </div>
                        <dl class="stats">
                            <div>
                                <dt>Subtopics mastered</dt>
                                <dd>
                                    {um?.subtopicsCleared ?? 0} / {um?.subtopicsTotal ??
                                        0}
                                </dd>
                            </div>
                            <div>
                                <dt>Exam importance</dt>
                                <dd>
                                    {(um?.weight ?? selectedUnit.weight).toFixed(1)} of 100
                                </dd>
                            </div>
                            <div>
                                <dt>Mastery by weight</dt>
                                <dd>{pct(um?.weightedMasteryPct ?? 0)}</dd>
                            </div>
                            <div>
                                <dt>Interleaving tier</dt>
                                <dd>
                                    {um?.mastered ? "cross-unit" : "within-unit"}
                                </dd>
                            </div>
                        </dl>
                        <button
                            class="study-btn"
                            on:click={() => practiceUnitTest(unitId)}
                            title="Practice test for this unit: exam-style problems interleaved across its subtopics; builds each subtopic's Performance."
                        >
                            Practice this unit
                        </button>
                        <button
                            class="study-btn secondary"
                            on:click={() => cramUnit(unitId)}
                            title="Review (memory): unlimited flashcard cram of this unit, never touches your spaced-repetition schedule or daily limits."
                        >
                            Review this unit
                        </button>
                    {:else if selectedLeaf}
                        {@const m = ev(selectedLeaf.tag)}
                        {@const full = subMap.get(selectedLeaf.tag)}
                        {@const c = leafColors.get(selectedLeaf.tag) ?? GREY}
                        {@const enough = hasEnoughEvidence(m)}
                        {@const studyTag = selectedLeaf.tag}
                        <div class="detail-head">
                            <div>
                                <h2>{selectedLeaf.name}</h2>
                                <p class="detail-unit">
                                    {units.find((u) => u.id === selectedLeaf?.unitId)
                                        ?.name} · exam weight
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
                                            need ≥ {MIN_PROBLEMS} reviews
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
                                            need ≥ {MIN_PROBLEMS} reviews
                                        </span>
                                    {/if}
                                    <span class="need">(need ≥ 90%)</span>
                                </dd>
                            </div>
                            <div>
                                <dt>Recall range</dt>
                                <dd>
                                    {#if enough}
                                        {pct(full?.recallLow ?? 0)}-{pct(
                                            full?.recallHigh ?? 0,
                                        )}
                                    {:else}
                                        <span class="pending">
                                            need ≥ {MIN_PROBLEMS} reviews
                                        </span>
                                    {/if}
                                    <span class="need">(10th-90th pct)</span>
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
                                <span class="perf-title">Performance</span>
                                <span
                                    class="perf-sep"
                                    style="color:{perfColor(
                                        toPerf(full),
                                    )}; font-weight:700"
                                >
                                    {perfStatusLabel(toPerf(full))}
                                </span>
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
                                    No graded practice questions yet. Take a practice
                                    test to build this signal.
                                </div>
                            {/if}
                        </div>

                        <p class="hint">
                            {#if !m || m.reviews === 0}
                                No reviews yet. Study this subtopic from the "SOA Exam
                                P" deck to start building evidence.
                            {:else if !enough}
                                Only {m.reviews} of {MIN_PROBLEMS} reviews so far: accuracy
                                and retention stay hidden until there's enough evidence to
                                judge them honestly.
                            {:else}
                                Keep reviewing until accuracy ≥ 80% and retention ≥ 90%
                                to clear the gate.
                            {/if}
                        </p>
                        <button
                            class="study-btn"
                            on:click={() => practiceTopic(studyTag)}
                            title="Practice test for this topic: exam-style problems that build its Performance score."
                        >
                            Practice this topic
                        </button>
                        <button
                            class="study-btn secondary"
                            on:click={() => cramSubtopic(studyTag)}
                            title="Review (memory): unlimited flashcard cram of this topic, never touches your spaced-repetition schedule or daily limits."
                        >
                            Review this topic
                        </button>
                    {/if}
                </section>
            {/if}
        </div>
    {/if}
</div>

<style>
    .study-map {
        position: relative;
        z-index: 0;
        max-width: 1180px;
        margin: 0 auto;
        padding: 2rem 1.5rem 4rem;
        color: var(--fg);
        font-family: var(--sr-font-body);
        font-size: 15px;
        line-height: 1.5;
        /* The two "what to do next" systems get deliberately far-apart hues so
           they can never read as two versions of one thing:
             • PERFORMANCE (practice) = warm amber, the practice track's own
               traffic-light hue (matches the dotted Performance rail key).
             • MEMORY (review) = cool periwinkle, the support/recall track hue
               (matches the solid Memory rail).
           `*-line` is the vivid accent (bars, icons, the solid CTA); `*-ink` is a
           deeper, text-legible shade of the same hue for labels. */
        --perf-line: #d3a95f;
        --perf-ink: #835f10;
        --mem-line: #7e88c9;
        --mem-ink: #4a5397;
    }
    /* On dark paper the ink shades lighten so coloured labels stay legible. */
    :global(.night-mode) .study-map {
        --perf-ink: #e6c17e;
        --mem-ink: #aab4ea;
    }

    /* Cram tab only (variant="cram"): make Cram read as one stacked reference
       surface with the Formula sheet that renders directly below it in the Home
       Cram tab. It gets the SAME full-bleed soap-ring backdrop the formula sheet
       uses, and the cram card is capped to the formula sheet's container width
       (900px) and centred, so the two line up. Scoped to .cram-view, so the
       radial map and the full /study-map view keep their own 1180px layout. */
    .study-map.cram-view {
        max-width: none;
        margin: 0;
        padding: 2rem 1.5rem 2.5rem;
        isolation: isolate;
        background:
            radial-gradient(
                120% 80% at 50% -12%,
                var(--sr-accent-weak),
                transparent 60%
            ),
            var(--canvas);
    }
    .study-map.cram-view::before {
        content: "";
        position: absolute;
        inset: 0;
        z-index: 0;
        pointer-events: none;
        background-image:
            radial-gradient(
                circle at 30% 32%,
                transparent 0 7px,
                var(--sr-accent-weak) 8px 9px,
                transparent 10px
            ),
            radial-gradient(
                circle at 72% 60%,
                transparent 0 11px,
                var(--sr-accent-weak) 12px 13px,
                transparent 14px
            ),
            radial-gradient(
                circle at 52% 86%,
                transparent 0 5px,
                var(--sr-accent-weak) 6px 7px,
                transparent 8px
            );
        background-size:
            150px 150px,
            220px 220px,
            120px 120px;
    }
    /* The cram card = the formula sheet's centred content column: same max-width,
       centred, lifted above the decorative ring layer. */
    .study-map.cram-view .memory {
        position: relative;
        z-index: 1;
        max-width: 900px;
        margin: 0 auto;
    }
    header {
        position: relative;
        z-index: 1;
        margin-bottom: 1.6rem;
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
        margin: 0.5rem 0 0;
        font-family: var(--sr-font-body);
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        color: var(--sr-accent);
    }
    .notice.error {
        position: relative;
        z-index: 1;
        border: var(--sr-border) solid var(--sr-quaternary);
        border-radius: var(--sr-radius);
        background: color-mix(in srgb, var(--sr-quaternary) 14%, transparent);
        padding: 0.85rem 1.1rem;
        margin-bottom: 1.25rem;
        font-weight: 600;
    }

    /* Readiness banner: the motivating headline at the top of the map. Calm by
       design (honesty core): a mint top-accent when a real score exists, an amber
       one when readiness is withheld, never a celebratory glow. The number is set
       in the body font with tabular figures, never the bubbly display font, and
       the full honesty bundle is one click away in the Evidence expander. */
    /* Top row: readiness on the left, the practice-next strip on the right, side
       by side on a wide screen. They wrap (readiness on top) once the row is too
       narrow to hold both. */
    .top-row {
        display: flex;
        flex-wrap: wrap;
        /* Cards keep their natural height (top-aligned). In the abstain state
           the readiness card's real content is shorter than the practice/review
           card, and stretching it to match only left an empty dark panel of
           dead space, so we let it size to its content (never padded with a
           fake score). */
        align-items: flex-start;
        gap: 1.25rem;
        margin: 0 0 1.25rem;
    }
    .top-row > .readiness-banner,
    .top-row > .focus-strip {
        margin: 0;
    }
    .top-row > .readiness-banner {
        flex: 3 1 20rem;
    }
    .top-row > .focus-strip {
        flex: 2 1 15rem;
    }
    .readiness-banner {
        position: relative;
        z-index: 1;
        margin: 0 0 1.25rem;
        border: 1px solid var(--border);
        border-radius: var(--sr-radius);
        background-color: var(--canvas-elevated);
        padding: 1.1rem 1.3rem;
        box-shadow:
            inset 0 3px 0 0 var(--sr-progress),
            var(--sr-shadow);
    }
    .readiness-banner.has-score {
        box-shadow:
            inset 0 3px 0 0 var(--sr-mastered),
            var(--sr-shadow);
    }
    .rb-top {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        justify-content: space-between;
        gap: 0.85rem 1.5rem;
    }
    .rb-headline {
        min-width: 0;
    }
    .rb-kicker {
        display: block;
        font-family: var(--sr-font-body);
        font-size: 0.7rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: var(--sr-mastered);
    }
    .rb-kicker.abstain {
        color: var(--sr-progress);
    }
    .rb-score {
        display: flex;
        align-items: baseline;
        gap: 0.4rem;
        margin-top: 0.2rem;
    }
    .rb-point {
        font-family: var(--sr-font-body);
        font-variant-numeric: tabular-nums;
        font-size: 2.2rem;
        font-weight: 800;
        line-height: 1;
        color: var(--fg);
    }
    .rb-outof {
        font-family: var(--sr-font-body);
        font-size: 1rem;
        font-weight: 700;
        color: var(--fg-subtle);
    }
    .rb-range {
        font-family: var(--sr-font-body);
        font-variant-numeric: tabular-nums;
        font-size: 1rem;
        font-weight: 600;
        color: var(--fg-subtle);
    }
    .rb-facts {
        margin-top: 0.4rem;
        font-size: 0.85rem;
        color: var(--fg-subtle);
    }
    .rb-facts b {
        color: var(--fg);
        font-variant-numeric: tabular-nums;
    }
    .rb-dot {
        margin: 0 0.4rem;
        color: var(--fg-subtle);
    }
    .rb-reason {
        margin: 0.3rem 0 0.6rem;
        color: var(--fg);
        font-size: 0.95rem;
    }
    .rb-gates {
        display: flex;
        flex-wrap: wrap;
        gap: 0.4rem 1.25rem;
    }
    .rb-gate {
        display: inline-flex;
        align-items: baseline;
        gap: 0.35rem;
        font-size: 0.85rem;
        color: var(--fg);
    }
    .rb-gate b {
        font-variant-numeric: tabular-nums;
    }
    .rb-gate-label {
        color: var(--fg-subtle);
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    .rb-gate-need {
        color: var(--fg-subtle);
        font-size: 0.78rem;
    }
    .rb-evidence {
        margin-top: 0.9rem;
        padding-top: 0.75rem;
        border-top: 1px solid var(--border-subtle);
    }
    .rb-toggle {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        border: 1px solid var(--border);
        background: var(--canvas-elevated);
        color: var(--sr-accent);
        font-family: var(--sr-font-body);
        font-weight: 700;
        font-size: 0.78rem;
        padding: 0.4rem 0.85rem;
        border-radius: var(--sr-radius-pill);
        cursor: pointer;
        transition:
            border-color 0.2s ease,
            background 0.2s ease;
    }
    .rb-toggle:hover {
        border-color: var(--sr-accent);
        background: var(--sr-accent-weak);
    }
    .rb-toggle:focus-visible {
        outline: 2px solid var(--sr-focus);
        outline-offset: 2px;
    }
    .rb-chevron {
        transition: transform 0.2s ease;
    }
    .rb-chevron.open {
        transform: rotate(180deg);
    }
    .rb-bundle {
        margin-top: 0.75rem;
        border: 1px solid var(--border);
        border-radius: var(--sr-radius);
        background: var(--canvas-elevated);
        padding: 0.2rem 1.1rem;
    }

    /* Shared maximalist panel base for the stacked info cards. Each panel sets
       its own clashing --panel-accent / --panel-shadow (systematic rotation). */
    .focus-strip,
    .overall,
    .memory,
    .plan,
    .pace {
        position: relative;
        z-index: 1;
        margin: 0 0 1.25rem;
        border: 1px solid var(--border);
        border-radius: var(--sr-radius);
        background-color: var(--canvas-elevated);
        /* 3px top-accent stripe as an inset shadow, so the section colour tucks
           neatly into the rounded top corners (a top-only accent, per the system). */
        box-shadow:
            inset 0 3px 0 0 var(--panel-accent, var(--sr-accent)),
            var(--sr-shadow);
    }

    /* Shared coloured marker: the icon that names WHICH system a cue belongs to.
       Performance = a trending-up arrow (raise your score); Memory = a
       rotate/refresh arrow (recall it again). Different SHAPE + different HUE, so
       they are distinguishable even in greyscale. */
    .rec-mark {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        flex: 0 0 auto;
        line-height: 0;
    }
    .rec-mark svg {
        width: 1.15em;
        height: 1.15em;
    }
    .rec-mark.perf {
        color: var(--perf-ink);
    }

    /* "What to do next" panel: a single big amber performance call-to-action. (The
       memory / review-due list that used to sit below it was removed as UI clutter;
       the memory signal still shows in the readiness bundle and the map's blue
       memory track.) */
    .focus-strip {
        --panel-accent: var(--perf-line);
        --panel-shadow: var(--sr-tertiary);
        padding: 1.1rem 1.3rem;
    }
    .rec-stack {
        display: flex;
        flex-direction: column;
        gap: 0.35rem;
    }
    .rec {
        display: flex;
        align-items: flex-start;
        gap: 0.7rem;
        border-radius: var(--sr-radius);
        padding: 0.8rem 0.9rem;
    }
    .rec .rec-mark {
        margin-top: 0.1rem;
    }
    .rec-main {
        flex: 1 1 auto;
        min-width: 0;
    }
    .rec-kicker {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        font-family: var(--sr-font-body);
        font-weight: 800;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }
    .rec-axis {
        font-size: 0.6rem;
        font-weight: 800;
        letter-spacing: 0.03em;
        padding: 0.1rem 0.45rem;
        border-radius: var(--sr-radius-pill);
        white-space: nowrap;
    }

    /* PRIMARY: performance / practice (the loud one). Emphasis comes from the
       warm tint + a TOP accent stripe (never a side stripe, per the system). */
    .rec-perf {
        background:
            linear-gradient(rgba(211, 169, 95, 0.12), rgba(211, 169, 95, 0.12)),
            var(--canvas-elevated);
        border: 1px solid rgba(211, 169, 95, 0.55);
        box-shadow: inset 0 3px 0 0 var(--perf-line);
    }
    .rec-perf .rec-mark {
        font-size: 1.4rem;
    }
    .rec-kicker.perf {
        font-size: 0.72rem;
        color: var(--perf-ink);
    }
    .rec-kicker.perf .rec-axis {
        color: var(--sr-on-warm);
        background: var(--perf-line);
    }
    .rec-cta {
        display: flex;
        flex-direction: row;
        flex-wrap: wrap;
        align-items: center;
        justify-content: space-between;
        gap: 0.25rem 1rem;
        width: 100%;
        margin: 0.5rem 0 0;
        padding: 0.7rem 1rem;
        border: 1px solid transparent;
        border-radius: var(--sr-radius-sm);
        background: var(--perf-line);
        color: var(--sr-on-warm);
        cursor: pointer;
        text-align: left;
        box-shadow: var(--sr-shadow-sm);
        transition:
            filter 0.18s ease,
            box-shadow 0.18s ease;
    }
    .rec-cta:hover {
        filter: brightness(1.05);
        box-shadow: var(--sr-shadow);
    }
    .rec-cta:active {
        transform: scale(0.995);
    }
    .rec-cta:focus-visible {
        outline: 2px solid var(--sr-focus);
        outline-offset: 2px;
    }
    .rec-topic {
        font-family: var(--sr-font-heading);
        font-weight: 700;
        font-size: 1.02rem;
        line-height: 1.15;
    }

    /* Overall mastery */
    .overall {
        --panel-accent: var(--sr-secondary);
        --panel-shadow: var(--sr-accent);
        padding: 1.4rem 1.5rem 1.5rem;
    }
    .overall-head {
        display: flex;
        align-items: baseline;
        justify-content: space-between;
        gap: 1rem;
    }
    .overall-head h2 {
        margin: 0;
        font-family: var(--sr-font-heading);
        font-size: 1.3rem;
        font-weight: 600;
        letter-spacing: -0.01em;
    }
    .overall-count {
        font-family: var(--sr-font-heading);
        font-weight: 800;
        font-size: 0.95rem;
    }
    .stack {
        display: flex;
        height: 12px;
        margin: 0.9rem 0 0.7rem;
        border-radius: var(--sr-radius-pill);
        overflow: hidden;
        border: 1px solid var(--border);
        background: var(--canvas-inset);
    }
    .stack .seg {
        height: 100%;
    }
    .overall-legend {
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem 0.85rem;
        font-size: 0.83rem;
        color: var(--fg-subtle);
    }
    .overall-legend b {
        font-weight: 800;
    }
    .overall-legend .sep {
        color: var(--border);
    }
    .focus {
        margin: 0.8rem 0 0;
        font-size: 0.88rem;
        display: flex;
        align-items: baseline;
        flex-wrap: wrap;
        gap: 0.4rem;
    }
    .focus-label {
        font-family: var(--sr-font-body);
        font-size: 0.66rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--sr-tertiary);
        background: transparent;
        border: 1px solid var(--sr-tertiary);
        border-radius: var(--sr-radius-pill);
        padding: 0.15rem 0.6rem;
    }
    .overall-note {
        margin: 0.8rem 0 0;
        font-size: 0.82rem;
        line-height: 1.45;
        color: var(--fg-subtle);
    }

    /* Memory (spaced repetition) */
    .memory {
        --panel-accent: var(--sr-tertiary);
        --panel-shadow: var(--sr-accent);
        padding: 1.4rem 1.5rem 1.5rem;
    }
    .memory-head {
        display: flex;
        align-items: baseline;
        justify-content: space-between;
        gap: 1rem;
    }
    .memory-head h2 {
        margin: 0;
        font-family: var(--sr-font-heading);
        font-size: 1.3rem;
        font-weight: 600;
        letter-spacing: -0.01em;
    }
    .memory-band {
        display: flex;
        align-items: baseline;
        gap: 0.6rem;
        margin-top: 0.8rem;
    }
    .memory-point {
        font-family: var(--sr-font-heading);
        font-size: 2rem;
        font-weight: 600;
        line-height: 1;
        color: var(--fg);
    }
    .memory-point.muted {
        font-size: 1.3rem;
        color: var(--fg-subtle);
    }
    .memory-range {
        font-size: 1rem;
        font-weight: 600;
        color: var(--fg-subtle);
    }
    .memory-detail {
        margin: 0.3rem 0 0;
        font-size: 0.8rem;
        color: var(--fg-subtle);
    }
    .memory-due {
        margin: 0.9rem 0 0;
        font-size: 0.9rem;
    }
    .memory-units {
        margin-top: 0.9rem;
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 0.4rem;
    }
    .memory-units-label {
        font-size: 0.66rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--fg-subtle);
        margin-right: 0.3rem;
    }
    .memory-unit {
        border: 1px solid var(--border);
        background: transparent;
        color: var(--fg);
        font-family: var(--sr-font-body);
        font-weight: 600;
        font-size: 0.8rem;
        padding: 0.4rem 0.8rem;
        border-radius: var(--sr-radius-sm);
        cursor: pointer;
        transition:
            border-color 0.2s ease,
            color 0.2s ease,
            background 0.2s ease;
    }
    .memory-unit:hover {
        border-color: var(--sr-tertiary);
        color: var(--sr-tertiary);
        background: var(--sr-accent-weak);
    }
    .memory-unit:focus-visible {
        outline: 2px solid var(--sr-focus);
        outline-offset: 2px;
    }
    /* Today's plan */
    .plan {
        --panel-accent: var(--sr-tertiary);
        --panel-shadow: var(--sr-quinary);
        padding: 1.4rem 1.5rem 1.5rem;
    }
    .plan-head {
        display: flex;
        align-items: baseline;
        justify-content: space-between;
        gap: 1rem;
    }
    .plan-head h2 {
        margin: 0;
        font-family: var(--sr-font-heading);
        font-size: 1.3rem;
        font-weight: 600;
        letter-spacing: -0.01em;
    }
    .tier {
        margin-top: 1rem;
    }
    .tier-head {
        display: flex;
        align-items: baseline;
        flex-wrap: wrap;
        gap: 0.45rem;
        margin-bottom: 0.4rem;
    }
    .tier-head b {
        font-family: var(--sr-font-body);
        font-weight: 700;
        font-size: 0.92rem;
    }
    .tier-dot {
        width: 10px;
        height: 10px;
        border-radius: 50%;
        align-self: center;
    }
    .tier-blurb {
        font-size: 0.78rem;
        color: var(--fg-subtle);
    }
    .plan-row {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        padding: 0.5rem 0;
        border-bottom: 2px dashed var(--border);
    }
    .tier .plan-row:last-child {
        border-bottom: none;
    }
    .plan-label {
        flex: 1 1 auto;
        font-weight: 700;
        font-size: 0.9rem;
    }
    .plan-count {
        flex: 0 0 auto;
        font-size: 0.8rem;
        color: var(--fg-subtle);
        white-space: nowrap;
    }
    .plan-study {
        flex: 0 0 auto;
        padding: 0.4rem 0.9rem;
        border: 1px solid var(--border);
        border-radius: var(--sr-radius-sm);
        background: var(--canvas-inset);
        color: var(--fg);
        font-family: var(--sr-font-body);
        font-weight: 600;
        font-size: 0.8rem;
        cursor: pointer;
        transition:
            background 0.2s ease,
            color 0.2s ease,
            border-color 0.2s ease;
    }
    .plan-study:hover {
        background: var(--sr-accent-strong);
        border-color: var(--sr-accent-strong);
        color: var(--sr-on-accent);
    }
    .plan-study:focus-visible {
        outline: 2px solid var(--sr-focus);
        outline-offset: 2px;
    }
    .plan-note {
        margin: 0.9rem 0 0;
        font-size: 0.78rem;
        line-height: 1.45;
        color: var(--fg-subtle);
    }
    .plan-caught-up {
        font-size: 0.85rem;
        color: var(--fg);
        border: 1px dashed var(--sr-secondary);
        border-radius: var(--sr-radius-sm);
        padding: 0.6rem 0.85rem;
        background: color-mix(in srgb, var(--sr-secondary) 8%, transparent);
    }
    .plan-more {
        margin-top: 0.9rem;
        padding: 0.5rem 1rem;
        border: 1px dashed var(--sr-secondary);
        border-radius: var(--sr-radius-sm);
        background: transparent;
        font-family: var(--sr-font-body);
        font-weight: 600;
        font-size: 0.8rem;
        cursor: pointer;
        color: var(--fg);
        transition:
            background 0.2s ease,
            color 0.2s ease;
    }
    .plan-more:hover {
        background: color-mix(in srgb, var(--sr-secondary) 16%, transparent);
        color: var(--fg);
    }
    .plan-more:focus-visible {
        outline: 2px solid var(--sr-focus);
        outline-offset: 2px;
    }

    /* Mastery pace */
    .pace {
        --panel-accent: var(--sr-quaternary);
        --panel-shadow: var(--sr-secondary);
        padding: 1.4rem 1.5rem 1.5rem;
    }
    .pace-head {
        display: flex;
        align-items: baseline;
        justify-content: space-between;
        gap: 1rem;
    }
    .pace-head h2 {
        margin: 0;
        font-family: var(--sr-font-heading);
        font-size: 1.3rem;
        font-weight: 600;
        letter-spacing: -0.01em;
    }
    .pace-badge {
        border-radius: var(--sr-radius-pill);
        padding: 0.25rem 0.7rem;
        font-family: var(--sr-font-body);
        font-size: 0.7rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        white-space: nowrap;
        border: 1px solid currentColor;
    }
    .pace-badge.ok {
        color: var(--sr-mastered);
    }
    .pace-badge.behind {
        color: var(--sr-progress);
    }
    .pace-badge.gathering {
        color: var(--sr-secondary);
    }
    .pace-badge.past {
        color: var(--fg-subtle);
    }
    .pace-row {
        display: flex;
        align-items: flex-end;
        gap: 0.75rem;
        margin: 0.8rem 0 0;
    }
    .pace-date {
        display: flex;
        flex-direction: column;
        gap: 0.25rem;
        font-family: var(--sr-font-heading);
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: var(--fg-subtle);
    }
    .pace-date input {
        font: inherit;
        font-size: 0.9rem;
        text-transform: none;
        letter-spacing: normal;
        padding: 0.5rem 0.6rem;
        border: 1px solid var(--border);
        border-radius: var(--sr-radius-sm);
        background: var(--canvas-inset);
        color: var(--fg);
    }
    .pace-date input:focus-visible {
        outline: 3px dashed var(--sr-focus);
        outline-offset: 2px;
    }
    .pace-clear {
        padding: 0.45rem 0.8rem;
        border: 1px solid var(--border);
        border-radius: var(--sr-radius-sm);
        background: transparent;
        color: var(--fg);
        font-family: var(--sr-font-body);
        font-weight: 600;
        font-size: 0.78rem;
        cursor: pointer;
    }
    .pace-clear:hover {
        border-color: var(--sr-accent);
    }
    .pace-detail {
        margin: 0.8rem 0 0;
        font-size: 0.9rem;
        line-height: 1.55;
        color: var(--fg);
    }
    /* A plain text paragraph (NOT flex): as a flex row each text run + <b> + any
       trailing punctuation becomes a separate flex item, so `gap` inserts a
       visible space before an attached "." ("…6.6/week ."). Normal inline flow
       keeps the punctuation tight against the value and wraps the sentence fine. */
    .pace-fix {
        margin: 0.6rem 0 0;
        font-size: 0.9rem;
        line-height: 1.5;
        color: var(--fg-subtle);
    }

    /* Concept map: map + detail share a row so the panel never covers bubbles. */
    .map-row {
        display: flex;
        align-items: flex-start;
        gap: 1.25rem;
        margin-bottom: 1.25rem;
    }
    .map-card {
        position: relative;
        z-index: 1;
        flex: 1 1 auto;
        min-width: 0;
        border: 1px solid var(--border);
        border-radius: var(--sr-radius);
        padding: 0.75rem 1rem;
        background-color: var(--canvas-elevated);
        background-image: radial-gradient(
            circle,
            rgba(129, 137, 214, 0.05) 1px,
            transparent 1.2px
        );
        background-size: 26px 26px;
        box-shadow: var(--sr-shadow);
    }
    /* Two-line connector legend (Memory vs Performance). Explains the two rails
       drawn between every pair of bubbles; sits above the diagram. */
    .track-legend {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 0.4rem 1.3rem;
        margin: 0.1rem 0.15rem 0.7rem;
        padding-bottom: 0.6rem;
        border-bottom: 1px dashed var(--border);
        font-size: 0.8rem;
        color: var(--fg-subtle);
    }
    .track-key {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
    }
    .track-key b {
        color: var(--fg);
        font-weight: 700;
    }
    /* Legend swatches are tiny SVGs drawn with the SAME stroke + dash pattern as
       the rails on the map, so each swatch matches its line exactly: Memory =
       solid periwinkle; Performance = dotted, tinted across the traffic-light
       range (struggling → practicing → strong). */
    .track-swatch {
        flex: 0 0 auto;
        display: block;
    }
    .track-hint {
        flex: 1 1 100%;
        font-size: 0.75rem;
        font-style: italic;
        line-height: 1.45;
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

    /* Bubble-colour key: what each fill colour means. Sits as a compact
       horizontal band directly above the diagram (outside the bubble area, below
       the two-line track legend), so its meaning stays next to the map and is
       always visible, yet it can never overlap a bubble at any window width (the
       reason it is no longer a corner overlay). */
    .map-key {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 0.35rem 1rem;
        margin: 0 0.15rem 0.6rem;
        font-size: 0.72rem;
        line-height: 1.2;
        color: var(--fg-subtle);
    }
    .map-key-item {
        display: flex;
        align-items: center;
        gap: 0.4rem;
        white-space: nowrap;
    }
    .map-key-dot {
        font-size: 0.9rem;
        line-height: 1;
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
        border: 2px solid var(--border);
        /* Rounded rectangles ("squircles"), not perfect circles, the full width
           gives labels room so they stop clipping. Rendered slightly inset
           (scale) with rounder corners so the shape fits inside its collision
           circle → adjacent bubbles keep a clear gap. */
        border-radius: 34%;
        padding: 8px;
        text-align: center;
        font-family: var(--sr-font-body);
        color: var(--fg);
        overflow: hidden;
        background: linear-gradient(var(--tint), var(--tint)), var(--canvas-elevated);
        box-shadow: var(--sr-shadow-sm);
        transform: scale(0.88);
    }
    /* Soap-bubble sheen: a soft top-left highlight clipped to the rounded shape,
       so each node reads as a glossy bubble. Decorative only. The base values are
       tuned for LIGHT mode, a white highlight on a pale bubble is low-contrast,
       so the specular is brighter and a touch bigger here so the gloss actually
       reads. It stays a small top-left ellipse fading to transparent, so the
       mastery fill/border colour underneath is never washed out. */
    .bubble::before,
    .leaf::before {
        content: "";
        position: absolute;
        top: 6%;
        left: 10%;
        width: 46%;
        height: 30%;
        border-radius: 50%;
        background: radial-gradient(
            circle at 33% 30%,
            rgba(255, 255, 255, 0.95),
            rgba(255, 255, 255, 0.28) 46%,
            rgba(255, 255, 255, 0) 76%
        );
        opacity: 0.9;
        pointer-events: none;
        z-index: 1;
    }
    /* Dark mode already showed the gloss well; keep its original, softer specular
       so the brighter light-mode highlight doesn't over-shine on dark paper. */
    :global(.night-mode) .bubble::before,
    :global(.night-mode) .leaf::before {
        top: 7%;
        left: 11%;
        width: 44%;
        height: 28%;
        background: radial-gradient(
            circle at 32% 32%,
            rgba(255, 255, 255, 0.5),
            rgba(255, 255, 255, 0) 72%
        );
        opacity: 0.7;
    }
    /* Light mode renders the white ::before specular as near-invisible on a
       near-white bubble, so the boxes lost the glossy dome that dark mode gets for
       free. This full-cover overlay restores it: a soft top-left specular plus a
       convex top-light, bottom-shaded gradient, so a light bubble domes like the
       dark one. */
    .bubble::after,
    .leaf::after {
        content: "";
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        pointer-events: none;
        z-index: 1;
        background:
            radial-gradient(
                44% 32% at 28% 19%,
                rgba(255, 255, 255, 1) 0%,
                rgba(255, 255, 255, 0.55) 42%,
                rgba(255, 255, 255, 0) 68%
            ),
            linear-gradient(
                158deg,
                rgba(18, 50, 78, 0.1) 0%,
                rgba(18, 50, 78, 0.05) 40%,
                rgba(18, 50, 78, 0.19) 100%
            );
    }
    /* Dark mode already domes via its ::before specular, so it skips this overlay. */
    :global(.night-mode) .bubble::after,
    :global(.night-mode) .leaf::after {
        background: none;
    }
    /* Keep the labels above the sheen. The absolutely-positioned .rec-badge is
       EXCLUDED, otherwise this would override its `position: absolute` and drop
       it into normal flow (where the bubble's overflow:hidden clips it). */
    .bubble > span,
    .leaf > span:not(.rec-badge) {
        position: relative;
        z-index: 2;
    }
    /* Node TITLES (centre / unit / subtopic) all use the heading font (Fredoka),
       so every bubble label reads as one type family. Small meta text (counts,
       "% of exam", legend, detail body) stays in the body font (Nunito), a
       coherent two-font scheme, no stray third font. */
    .node-title {
        font-family: var(--sr-font-heading);
        font-weight: 600;
        font-size: 0.82rem;
        line-height: 1.14;
    }
    .node-sub {
        font-size: 0.72rem;
        color: var(--fg-subtle);
    }
    .node-pct {
        font-family: var(--sr-font-body);
        font-size: 0.7rem;
        font-weight: 700;
        line-height: 1.15;
        color: var(--sr-accent);
    }
    .bubble.center {
        border-width: 2px;
        box-shadow: var(--sr-shadow);
        cursor: pointer;
        transition:
            box-shadow 0.18s ease,
            transform 0.18s ease;
    }
    .bubble.center:hover {
        box-shadow:
            0 0 0 3px var(--tint),
            var(--sr-shadow);
        transform: scale(0.93);
    }
    .bubble.center:focus-visible {
        outline: 2px solid var(--sr-focus);
        outline-offset: 2px;
    }
    .bubble.center .node-title {
        font-family: var(--sr-font-heading);
        font-size: 1.2rem;
        font-weight: 600;
    }
    .center-cta {
        margin-top: 2px;
        font-size: 0.6rem;
        font-weight: 800;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        color: var(--sr-accent);
        opacity: 0.9;
    }
    .bubble.unit {
        cursor: pointer;
        transition:
            box-shadow 0.18s ease,
            transform 0.18s ease;
    }
    .bubble.unit .node-title {
        font-size: 1rem;
    }
    .bubble.unit:hover {
        box-shadow:
            0 0 0 3px var(--tint),
            var(--sr-shadow);
        transform: translateY(-2px) scale(0.9);
    }
    .bubble.unit.selected {
        box-shadow:
            0 0 0 2px var(--sr-accent),
            var(--sr-shadow-sm);
    }

    /* Subtopic: the smallest tier, a compact bubble with its label INSIDE it. */
    .leaf {
        position: absolute;
        box-sizing: border-box;
        display: flex;
        align-items: center;
        justify-content: center;
        text-align: center;
        padding: 6px;
        border: 2px solid var(--border);
        border-radius: 34%;
        background: linear-gradient(var(--tint), var(--tint)), var(--canvas-elevated);
        box-shadow: var(--sr-shadow-sm);
        font-family: var(--sr-font-heading);
        color: var(--fg);
        cursor: pointer;
        overflow: hidden;
        transform: scale(0.88);
        transition:
            box-shadow 0.18s ease,
            transform 0.18s ease;
    }
    .leaf-label {
        font-family: var(--sr-font-heading);
        font-size: 0.72rem;
        line-height: 1.16;
        font-weight: 600;
        overflow-wrap: break-word;
        hyphens: auto;
        color: var(--fg);
    }
    .leaf:hover {
        box-shadow:
            0 0 0 3px var(--tint),
            var(--sr-shadow-sm);
        transform: scale(1);
        z-index: 3;
    }
    .leaf.selected {
        box-shadow:
            0 0 0 2px var(--sr-accent),
            var(--sr-shadow-sm);
        transform: scale(0.94);
        z-index: 3;
    }
    .leaf.selected .leaf-label {
        font-weight: 700;
    }
    /* The one recommended-next topic gets a warm amber glow/pulse on its bubble,
       the same performance hue as the "Practice next" CTA, so the single place to
       practice next is unmistakable. A small "next" pill labels it as well. */
    .leaf.rec-next {
        z-index: 2;
        box-shadow:
            0 0 0 4px rgba(211, 169, 95, 0.85),
            0 0 20px 6px rgba(211, 169, 95, 0.6),
            var(--sr-shadow-sm);
        animation: focusPulse 1.8s ease-in-out infinite;
    }
    @keyframes focusPulse {
        0%,
        100% {
            box-shadow:
                0 0 0 4px rgba(211, 169, 95, 0.85),
                0 0 20px 6px rgba(211, 169, 95, 0.55),
                var(--sr-shadow-sm);
        }
        50% {
            box-shadow:
                0 0 0 7px rgba(211, 169, 95, 0.6),
                0 0 34px 12px rgba(211, 169, 95, 0.42),
                var(--sr-shadow-sm);
        }
    }
    .rec-badge {
        position: absolute;
        top: 6px;
        left: 50%;
        transform: translateX(-50%);
        font-family: var(--sr-font-body);
        font-size: 0.56rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: var(--perf-ink);
        background: var(--canvas-elevated);
        border: 1px solid var(--perf-line);
        border-radius: var(--sr-radius-pill);
        padding: 0.05rem 0.4rem;
        line-height: 1.35;
        /* Above the bubble sheen (::before, z-index 1) so it's never washed out. */
        z-index: 3;
    }

    /* Dim bubbles outside the selected subtopic's prerequisite chain. */
    .leaf.dim {
        opacity: 0.3;
    }

    /* Detail: an inline panel beside the map (sticky while you scroll). It shares
       the map row, so opening it shrinks the map instead of covering bubbles. */
    .detail {
        flex: 0 0 340px;
        align-self: flex-start;
        position: sticky;
        top: 1rem;
        max-height: calc(100vh - 110px);
        overflow-y: auto;
        border: 1px solid var(--border);
        border-radius: var(--sr-radius);
        padding: 1.35rem 1.45rem;
        background-color: var(--canvas-elevated);
        box-shadow:
            inset 0 3px 0 0 var(--sr-accent),
            var(--sr-shadow);
        animation: popIn 0.16s ease;
    }
    @media (max-width: 900px) {
        .map-row {
            flex-wrap: wrap;
        }
        .detail {
            flex-basis: 100%;
            position: static;
            max-height: none;
        }
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
        right: 8px;
        /* A comfortable, centred tap target. Reserve a transparent border so the
           global button:hover (adds a 1px border) can't resize it on hover. */
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 30px;
        height: 30px;
        border: 1px solid transparent;
        border-radius: var(--sr-radius-sm);
        background: transparent;
        font-size: 1.4rem;
        line-height: 1;
        cursor: pointer;
        color: var(--fg-subtle);
        transition:
            color 0.18s ease,
            background 0.18s ease;
    }
    .detail-close:hover {
        color: var(--sr-accent);
        background: var(--sr-accent-weak);
        border-color: transparent;
    }
    .detail-head {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 1rem;
        /* Keep the right-aligned status pill clear of the absolutely-positioned
           close × in the top-right corner, the pill's right edge is fixed, so
           this holds for the longest label ("gathering data (9/10)") too. */
        padding-right: 2.25rem;
    }
    .detail-head h2 {
        margin: 0;
        font-family: var(--sr-font-heading);
        font-size: 1.25rem;
        font-weight: 600;
        letter-spacing: -0.01em;
        line-height: 1.1;
    }
    .detail-unit {
        margin: 0.3rem 0 0;
        font-size: 0.8rem;
        color: var(--fg-subtle);
    }
    .pill {
        border: 1px solid currentColor;
        border-radius: var(--sr-radius-pill);
        padding: 0.22rem 0.7rem;
        font-family: var(--sr-font-body);
        font-size: 0.7rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        white-space: nowrap;
    }
    .stats {
        margin: 0.9rem 0 0;
    }
    .stats > div {
        display: flex;
        justify-content: space-between;
        gap: 1rem;
        padding: 0.5rem 0;
        border-bottom: 2px dashed var(--border);
    }
    .stats > div:last-child {
        border-bottom: none;
    }
    .stats dt {
        color: var(--fg-subtle);
    }
    .stats dd {
        margin: 0;
        font-weight: 800;
    }
    .stats .need {
        font-weight: 400;
        font-size: 0.78rem;
        color: var(--fg-subtle);
    }
    .stats .pending {
        font-weight: 400;
        font-style: italic;
        color: var(--fg-subtle);
    }
    .hint {
        margin: 0.85rem 0 0;
        font-size: 0.82rem;
        color: var(--fg-subtle);
    }

    /* Performance (practice tests): a SEPARATE panel from the memory-gate
       stats above, so the two signals never read as one blended number. */
    .perf {
        margin: 0.9rem 0 0;
        padding: 0.7rem 0.85rem;
        border: 1px solid var(--border);
        border-radius: var(--sr-radius-sm);
        background: var(--canvas-inset);
    }
    .perf-head {
        display: flex;
        align-items: baseline;
        justify-content: space-between;
        gap: 0.5rem;
    }
    .perf-title {
        font-family: var(--sr-font-body);
        font-weight: 700;
        font-size: 0.82rem;
    }
    .perf-sep {
        font-size: 0.68rem;
        color: var(--fg-subtle);
    }
    .perf-body {
        margin-top: 0.35rem;
        font-size: 0.86rem;
    }
    .perf-body.pending {
        font-style: italic;
        color: var(--fg-subtle);
        font-size: 0.8rem;
    }

    /* Primary study CTA: solid periwinkle, paper label (AA-legible). */
    .study-btn {
        margin-top: 1.1rem;
        width: 100%;
        min-height: 46px;
        padding: 0.7rem 1rem;
        border: 1px solid transparent;
        border-radius: var(--sr-radius);
        background: var(--sr-accent-strong);
        color: var(--sr-on-accent);
        font-family: var(--sr-font-body);
        font-weight: 700;
        font-size: 0.9rem;
        cursor: pointer;
        box-shadow: var(--sr-shadow-sm);
        transition:
            background 0.2s ease,
            box-shadow 0.2s ease;
    }
    .study-btn:hover:not(:disabled) {
        background: var(--sr-accent-strong-2);
        box-shadow: var(--sr-shadow);
    }
    .study-btn:active:not(:disabled) {
        transform: scale(0.99);
    }
    .study-btn:focus-visible {
        outline: 2px solid var(--sr-focus);
        outline-offset: 2px;
    }
    /* Caught-up / nothing-due: clearly not clickable, so a study button never
       leads to an empty deck. */
    .study-btn:disabled {
        background: var(--canvas-inset);
        color: var(--fg-subtle);
        box-shadow: none;
        cursor: not-allowed;
    }
    .study-btn.secondary {
        margin-top: 0.7rem;
        background: transparent;
        color: var(--fg);
        border: 1px solid var(--border);
        box-shadow: none;
    }
    .study-btn.secondary:hover:not(:disabled) {
        background: var(--sr-accent-weak);
        border-color: var(--sr-accent);
        color: var(--fg);
    }
    .study-btn.secondary:disabled {
        background: transparent;
        color: var(--fg-subtle);
        border-color: var(--border-subtle);
    }
</style>
