<!--
Copyright: Ankitects Pty Ltd and contributors
License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
-->
<script lang="ts">
    import { onMount } from "svelte";

    import { getMasteryState } from "@generated/backend";
    import type { MasteryState, SubtopicMastery } from "@generated/anki/speedrun_pb";

    // Mirrors pylib/anki/speedrun/exam_p_topics.json (official 2026-05 outline).
    // Display names are shortened to fit map nodes. A future RPC will serve the
    // syllabus so there is a single source of truth.
    const TAXONOMY = [
        {
            id: "general",
            name: "General Probability",
            subtopics: [
                { id: "sets_axioms", name: "Sets & axioms" },
                { id: "combinatorics", name: "Combinatorics" },
                { id: "independence", name: "Independence" },
                { id: "add_mult_rules", name: "Addition & multiplication" },
                { id: "conditional", name: "Conditional probability" },
                { id: "bayes", name: "Bayes' theorem" },
            ],
        },
        {
            id: "univariate",
            name: "Univariate RVs",
            subtopics: [
                { id: "rv_basics", name: "PDFs & CDFs" },
                { id: "expectation", name: "Expectation & moments" },
                { id: "variance", name: "Variance & SD" },
                { id: "discrete_dists", name: "Discrete distributions" },
                { id: "continuous_dists", name: "Continuous distributions" },
                { id: "insurance_apps", name: "Insurance applications" },
            ],
        },
        {
            id: "multivariate",
            name: "Multivariate RVs",
            subtopics: [
                { id: "joint_distributions", name: "Joint distributions" },
                { id: "marginal_conditional", name: "Marginal & conditional" },
                { id: "joint_moments", name: "Joint moments" },
                { id: "covariance_correlation", name: "Covariance & correlation" },
                { id: "order_statistics", name: "Order statistics" },
                { id: "linear_combinations", name: "Linear combinations" },
                { id: "clt", name: "Central limit theorem" },
            ],
        },
    ];

    // A calmer, cohesive palette (traffic-light meaning, softened).
    const GREY = "#a7b2c2"; // not started
    const AMBER = "#e0a552"; // in progress
    const GREEN = "#57a37c"; // mastered
    const ACCENT = "#6486bf"; // the central node

    // --- radial concept-map layout: Exam P at the centre, the 3 units on an
    // equilateral triangle around it, each unit's subtopics fanning outward. ---
    const DEG = Math.PI / 180;
    const CANVAS_W = 920;
    const CANVAS_H = 900;
    const CX = CANVAS_W / 2;
    const CY = CANVAS_H / 2 + 4;
    const R_UNIT = 160;
    const R_SUB = 300;
    const R_STAGGER = 64;
    // Top, bottom-right, bottom-left -> an upward-pointing equilateral triangle.
    const UNIT_ANGLES = [-90, 30, 150];

    interface LeafNode {
        id: string;
        name: string;
        tag: string;
        unitId: string;
        x: number;
        y: number;
    }
    interface UnitNode {
        id: string;
        name: string;
        x: number;
        y: number;
        subs: LeafNode[];
    }

    const units: UnitNode[] = TAXONOMY.map((u, i) => {
        const baseDeg = UNIT_ANGLES[i];
        const a = baseDeg * DEG;
        const ux = CX + R_UNIT * Math.cos(a);
        const uy = CY + R_UNIT * Math.sin(a);
        const n = u.subtopics.length;
        const spread = Math.min(96, (n - 1) * 18);
        const step = n > 1 ? spread / (n - 1) : 0;
        const subs: LeafNode[] = u.subtopics.map((s, j) => {
            const sa = (baseDeg + (j - (n - 1) / 2) * step) * DEG;
            const r = R_SUB + (j % 2) * R_STAGGER;
            return {
                id: s.id,
                name: s.name,
                tag: `subtopic::${u.id}::${s.id}`,
                unitId: u.id,
                x: CX + r * Math.cos(sa),
                y: CY + r * Math.sin(sa),
            };
        });
        return { id: u.id, name: u.name, x: ux, y: uy, subs };
    });

    const allTags = units.flatMap((u) => u.subs.map((s) => s.tag));

    let result: MasteryState | null = null;
    let loadError = "";
    let selected: LeafNode | null = null;

    onMount(async () => {
        try {
            result = await getMasteryState({ expectedSubtopics: allTags });
        } catch (err) {
            loadError = String(err);
        }
    });

    $: subMap = new Map<string, SubtopicMastery>(
        (result?.subtopics ?? []).map((s) => [s.tag, s]),
    );
    $: unitMap = new Map((result?.units ?? []).map((u) => [u.unitId, u]));

    function leafProgress(tag: string): number {
        const m = subMap.get(tag);
        if (!m) {
            return 0;
        }
        if (m.gateCleared) {
            return 1;
        }
        if (m.reviews === 0) {
            return 0;
        }
        const parts = [
            Math.min(m.reviews / 10, 1),
            Math.min(m.accuracy / 0.8, 1),
            Math.min(m.meanRetrievability / 0.9, 1),
        ];
        const avg = parts.reduce((a, b) => a + b, 0) / parts.length;
        return Math.min(0.95, avg);
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

    // Shorten a segment so it starts/ends at the node boundaries, not centres,
    // and carries a progress fraction for the coloured (length-proportional) part.
    interface Edge {
        x1: number;
        y1: number;
        x2: number;
        y2: number;
        progress: number;
        color: string;
    }
    function segment(
        x1: number,
        y1: number,
        x2: number,
        y2: number,
        r1: number,
        r2: number,
        progress: number,
        color: string,
    ): Edge {
        const dx = x2 - x1;
        const dy = y2 - y1;
        const len = Math.hypot(dx, dy) || 1;
        const ux = dx / len;
        const uy = dy / len;
        return {
            x1: x1 + ux * r1,
            y1: y1 + uy * r1,
            x2: x2 - ux * r2,
            y2: y2 - uy * r2,
            progress,
            color,
        };
    }

    $: edges = [
        ...units.map((u): Edge => {
            const p = unitProgress(u.id);
            return segment(
                CX,
                CY,
                u.x,
                u.y,
                42,
                46,
                p,
                colorFor(p, unitMap.get(u.id)?.mastered ?? false),
            );
        }),
        ...units.flatMap((u) =>
            u.subs.map((s): Edge => {
                const p = leafProgress(s.tag);
                return segment(
                    u.x,
                    u.y,
                    s.x,
                    s.y,
                    46,
                    40,
                    p,
                    colorFor(p, leafCleared(s.tag)),
                );
            }),
        ),
    ];

    function pct(x: number): string {
        return `${Math.round(x * 100)}%`;
    }

    function leafStatus(tag: string): string {
        const m = subMap.get(tag);
        if (!m || m.reviews === 0) {
            return "not started";
        }
        if (m.gateCleared) {
            return "mastered";
        }
        return `${pct(leafProgress(tag))} to gate`;
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
            Tap a subtopic to see its mastery. Each link fills along its length as you
            clear the gate:
            <span class="key" style="color:{GREY}">■</span>
            not started,
            <span class="key" style="color:{AMBER}">■</span>
            in progress,
            <span class="key" style="color:{GREEN}">■</span>
            mastered.
        </p>
    </header>

    {#if loadError}
        <div class="notice error">Couldn't load mastery: {loadError}</div>
    {/if}

    <div class="canvas-wrap">
        <div class="canvas" style="width:{CANVAS_W}px; height:{CANVAS_H}px;">
            <svg
                class="edges"
                viewBox="0 0 {CANVAS_W} {CANVAS_H}"
                width={CANVAS_W}
                height={CANVAS_H}
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
                        opacity="0.5"
                    />
                    {#if e.progress > 0}
                        <line
                            x1={e.x1}
                            y1={e.y1}
                            x2={e.x1 + e.progress * (e.x2 - e.x1)}
                            y2={e.y1 + e.progress * (e.y2 - e.y1)}
                            stroke={e.color}
                            stroke-width="3"
                            stroke-linecap="round"
                        />
                    {/if}
                {/each}
            </svg>

            <!-- centre -->
            <div
                class="node center"
                style="left:{CX - 58}px; top:{CY - 24}px; border-color:{ACCENT};
                       --tint:{ACCENT}1f;"
            >
                <span class="node-title">Exam P</span>
            </div>

            <!-- units -->
            {#each units as u}
                {@const up = unitProgress(u.id)}
                {@const uc = colorFor(up, unitMap.get(u.id)?.mastered ?? false)}
                <div
                    class="node unit"
                    style="left:{u.x - 78}px; top:{u.y - 26}px;
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
                    {@const p = leafProgress(s.tag)}
                    {@const c = colorFor(p, leafCleared(s.tag))}
                    <button
                        class="node leaf"
                        class:selected={selected?.tag === s.tag}
                        style="left:{s.x - 72}px; top:{s.y - 24}px;
                               border-color:{c}; --tint:{c}1a;"
                        on:click={() => select(s)}
                    >
                        <span class="node-title">{s.name}</span>
                        <span class="node-sub">{leafStatus(s.tag)}</span>
                    </button>
                {/each}
            {/each}
        </div>
    </div>

    {#if selected}
        {@const m = subMap.get(selected.tag)}
        {@const c = colorFor(leafProgress(selected.tag), leafCleared(selected.tag))}
        <section class="detail">
            <div class="detail-head">
                <div>
                    <h2>{selected.name}</h2>
                    <p class="detail-unit">
                        {units.find((u) => u.id === selected?.unitId)?.name}
                    </p>
                </div>
                <span class="pill" style="background:{c}22; color:{c};">
                    {leafStatus(selected.tag)}
                </span>
            </div>
            <dl class="stats">
                <div>
                    <dt>Graded reviews</dt>
                    <dd>
                        {m?.reviews ?? 0}
                        <span class="need">(need ≥ 10)</span>
                    </dd>
                </div>
                <div>
                    <dt>Accuracy</dt>
                    <dd>
                        {m ? pct(m.accuracy) : "—"}
                        <span class="need">(need ≥ 80%)</span>
                    </dd>
                </div>
                <div>
                    <dt>Mean retrievability</dt>
                    <dd>
                        {m ? pct(m.meanRetrievability) : "—"}
                        <span class="need">(need ≥ 90%)</span>
                    </dd>
                </div>
                <div>
                    <dt>Gate</dt>
                    <dd>{m?.gateCleared ? "cleared" : "not cleared"}</dd>
                </div>
            </dl>
            <p class="hint">
                Opening this subtopic's deck straight from the map is coming next — for
                now, study it from the deck list ("SOA Exam P").
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
        max-width: 940px;
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
    .canvas-wrap {
        overflow: auto;
        display: flex;
        justify-content: center;
    }
    .canvas {
        position: relative;
        flex: 0 0 auto;
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
        justify-content: center;
        gap: 2px;
        border: 2px solid var(--border, #e2e2e5);
        border-radius: 12px;
        background: var(--canvas-elevated, #fbfbfc);
        padding: 6px 10px;
        text-align: center;
        font: inherit;
        color: inherit;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
    }
    .node-title {
        font-weight: 600;
        font-size: 0.82rem;
        line-height: 1.15;
    }
    .node-sub {
        font-size: 0.68rem;
        color: var(--fg-subtle, #6b7280);
    }
    .node.center {
        width: 116px;
        height: 48px;
        align-items: center;
        background:
            linear-gradient(var(--tint), var(--tint)), var(--canvas-elevated, #fbfbfc);
    }
    .node.center .node-title {
        font-size: 1rem;
        font-weight: 700;
    }
    .node.unit {
        width: 156px;
        height: 52px;
        align-items: center;
        background:
            linear-gradient(var(--tint), var(--tint)), var(--canvas-elevated, #fbfbfc);
    }
    .node.unit .node-title {
        font-size: 0.9rem;
    }
    button.node.leaf {
        width: 144px;
        min-height: 48px;
        cursor: pointer;
        align-items: center;
        background:
            linear-gradient(var(--tint), var(--tint)), var(--canvas-elevated, #fbfbfc);
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
