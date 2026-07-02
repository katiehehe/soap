// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

// Pure geometry for the study-map concept map. Kept out of the Svelte component
// so the layout can be unit-tested: bubbles must never overlap, every bubble
// must fit inside the canvas, every edge must touch the borders of the two
// bubbles it connects, and a bubble's radius must grow with its exam-importance
// weight (size = importance; the fill colour, added in the component, = measured
// mastery — the two are never conflated).

export interface SubtopicDef {
    id: string;
    name: string;
    // Relative exam-importance weight. Mirrors the "weight" field in
    // pylib/anki/speedrun/exam_p_topics.json (an editable emphasis estimate;
    // each unit's subtopic weights sum to its official section midpoint).
    weight: number;
    // Prerequisite subtopic ids WITHIN the same unit (the guided-learning DAG).
    // Mirrors "prereqs" in pylib/anki/speedrun/exam_p_topics.json; cross-unit
    // order is expressed by UNIT_PREREQS below.
    prereqs: string[];
}
export interface UnitDef {
    id: string;
    name: string;
    subtopics: SubtopicDef[];
}

// Mirrors pylib/anki/speedrun/exam_p_topics.json (official 2026-05 outline).
// Names are kept short so they read well beneath a bubble; weights + prereqs
// mirror the JSON so the map draws the same DAG the engine gates on.
export const TAXONOMY: UnitDef[] = [
    {
        id: "general",
        name: "General Probability",
        subtopics: [
            { id: "sets_axioms", name: "Sets & axioms", weight: 3.5, prereqs: [] },
            {
                id: "combinatorics",
                name: "Combinatorics",
                weight: 4.5,
                prereqs: ["sets_axioms"],
            },
            {
                id: "independence",
                name: "Independence",
                weight: 4.0,
                prereqs: ["add_mult_rules"],
            },
            {
                id: "add_mult_rules",
                name: "Addition & mult. rules",
                weight: 4.0,
                prereqs: ["sets_axioms"],
            },
            {
                id: "conditional",
                name: "Conditional prob.",
                weight: 5.25,
                prereqs: ["add_mult_rules"],
            },
            {
                id: "bayes",
                name: "Bayes' theorem",
                weight: 5.25,
                prereqs: ["conditional"],
            },
        ],
    },
    {
        id: "univariate",
        name: "Univariate RVs",
        subtopics: [
            { id: "rv_basics", name: "PDFs & CDFs", weight: 6.5, prereqs: [] },
            {
                id: "expectation",
                name: "Expectation & moments",
                weight: 8.5,
                prereqs: ["rv_basics"],
            },
            {
                id: "variance",
                name: "Variance & SD",
                weight: 7.0,
                prereqs: ["expectation"],
            },
            {
                id: "discrete_dists",
                name: "Discrete dist.",
                weight: 9.0,
                prereqs: ["variance"],
            },
            {
                id: "continuous_dists",
                name: "Continuous dist.",
                weight: 9.0,
                prereqs: ["variance"],
            },
            {
                id: "insurance_apps",
                name: "Insurance apps",
                weight: 7.0,
                prereqs: ["continuous_dists"],
            },
        ],
    },
    {
        id: "multivariate",
        name: "Multivariate RVs",
        subtopics: [
            {
                id: "joint_distributions",
                name: "Joint distributions",
                weight: 4.25,
                prereqs: [],
            },
            {
                id: "marginal_conditional",
                name: "Marginal & cond.",
                weight: 4.25,
                prereqs: ["joint_distributions"],
            },
            {
                id: "joint_moments",
                name: "Joint moments",
                weight: 3.5,
                prereqs: ["marginal_conditional"],
            },
            {
                id: "covariance_correlation",
                name: "Covariance & corr.",
                weight: 4.25,
                prereqs: ["joint_moments"],
            },
            {
                id: "order_statistics",
                name: "Order statistics",
                weight: 2.75,
                prereqs: ["marginal_conditional"],
            },
            {
                id: "linear_combinations",
                name: "Linear combos",
                weight: 3.75,
                prereqs: ["covariance_correlation"],
            },
            {
                id: "clt",
                name: "Central limit thm.",
                weight: 3.75,
                prereqs: ["linear_combinations"],
            },
        ],
    },
];

// Cross-unit curriculum order (mirrors each unit's "prereqs" in the topic map):
// univariate needs general; multivariate needs univariate.
export const UNIT_PREREQS: Record<string, string[]> = {
    general: [],
    univariate: ["general"],
    multivariate: ["univariate"],
};

// A calmer, cohesive palette (traffic-light meaning, softened).
export const COLORS = {
    grey: "#a7b2c2", // not started
    amber: "#e0a552", // in progress
    green: "#57a37c", // mastered
    accent: "#6486bf", // the central node
};

/** Total importance weight of a unit = the sum of its subtopic weights (which,
 * by construction in the topic map, equals the unit's official section
 * midpoint). */
export function unitWeight(u: UnitDef): number {
    return u.subtopics.reduce((sum, s) => sum + s.weight, 0);
}

// Bubble radii. Importance maps to radius through the observed weight ranges so
// the biggest exam topics read as the biggest bubbles. Radii are capped well
// below the spacing between bubble centres (see the radial constants) so no two
// bubbles can overlap — verified by lib.test.ts.
export const CENTER_R = 58;
const UNIT_R_MIN = 54;
const UNIT_R_MAX = 72;
const SUB_R_MIN = 50;
const SUB_R_MAX = 74;

const SUB_WEIGHTS = TAXONOMY.flatMap((u) => u.subtopics.map((s) => s.weight));
const SUB_W_MIN = Math.min(...SUB_WEIGHTS);
const SUB_W_MAX = Math.max(...SUB_WEIGHTS);
const UNIT_WEIGHTS = TAXONOMY.map(unitWeight);
const UNIT_W_MIN = Math.min(...UNIT_WEIGHTS);
const UNIT_W_MAX = Math.max(...UNIT_WEIGHTS);

function clamp01(t: number): number {
    return Math.max(0, Math.min(1, t));
}
function lerp(t: number, lo: number, hi: number): number {
    return lo + (hi - lo) * clamp01(t);
}
function norm(x: number, lo: number, hi: number): number {
    return hi > lo ? (x - lo) / (hi - lo) : 0.5;
}

/** Bubble radius for a subtopic, increasing with its importance weight. */
export function subRadius(weight: number): number {
    return lerp(norm(weight, SUB_W_MIN, SUB_W_MAX), SUB_R_MIN, SUB_R_MAX);
}
/** Bubble radius for a unit, increasing with its total importance weight. */
export function unitRadius(weight: number): number {
    return lerp(norm(weight, UNIT_W_MIN, UNIT_W_MAX), UNIT_R_MIN, UNIT_R_MAX);
}

// Radial layout constants. Two rings (near/far) per unit halve the number of
// bubbles competing for angular space; the generous radii leave room for the
// largest bubbles without overlap (verified by lib.test.ts).
const R_UNIT = 250;
const R_IN = 450;
const R_OUT = 640;
const STEP_DEG = 17; // angular gap between consecutive subtopics of a unit
const UNIT_ANGLES_DEG = [-90, 30, 150]; // upward-pointing equilateral triangle
const MARGIN = 26;
const DEG = Math.PI / 180;

export interface Circle {
    x: number; // centre
    y: number;
    r: number;
}
export interface LeafNode extends Circle {
    id: string;
    name: string;
    tag: string;
    unitId: string;
    weight: number;
    // Prerequisite subtopic tags (full `subtopic::unit::id` tags).
    prereqs: string[];
}
export interface UnitNode extends Circle {
    id: string;
    name: string;
    weight: number;
    subs: LeafNode[];
}
export interface Layout {
    center: Circle;
    units: UnitNode[];
    width: number;
    height: number;
}

export function subtopicTag(unitId: string, subId: string): string {
    return `subtopic::${unitId}::${subId}`;
}

/** Compute absolute bubble positions with the whole diagram shifted into a
 * positive, margin-padded canvas. */
export function computeLayout(): Layout {
    // 1. lay out around origin (0,0 = centre bubble)
    const center: Circle = { x: 0, y: 0, r: CENTER_R };
    const units: UnitNode[] = TAXONOMY.map((u, i) => {
        const base = UNIT_ANGLES_DEG[i];
        const ux = R_UNIT * Math.cos(base * DEG);
        const uy = R_UNIT * Math.sin(base * DEG);
        const n = u.subtopics.length;
        const subs: LeafNode[] = u.subtopics.map((s, j) => {
            const angle = (base + (j - (n - 1) / 2) * STEP_DEG) * DEG;
            const r = j % 2 === 0 ? R_IN : R_OUT;
            return {
                id: s.id,
                name: s.name,
                tag: subtopicTag(u.id, s.id),
                unitId: u.id,
                weight: s.weight,
                prereqs: s.prereqs.map((p) => subtopicTag(u.id, p)),
                x: r * Math.cos(angle),
                y: r * Math.sin(angle),
                r: subRadius(s.weight),
            };
        });
        const w = unitWeight(u);
        return {
            id: u.id,
            name: u.name,
            weight: w,
            x: ux,
            y: uy,
            r: unitRadius(w),
            subs,
        };
    });

    // 2. measure bounds over every bubble (centre +/- radius)
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    const measure = (c: Circle) => {
        minX = Math.min(minX, c.x - c.r);
        maxX = Math.max(maxX, c.x + c.r);
        minY = Math.min(minY, c.y - c.r);
        maxY = Math.max(maxY, c.y + c.r);
    };
    measure(center);
    for (const u of units) {
        measure(u);
        u.subs.forEach(measure);
    }

    // 3. shift into positive space with a margin
    const dx = MARGIN - minX;
    const dy = MARGIN - minY;
    const shift = (c: Circle) => {
        c.x += dx;
        c.y += dy;
    };
    shift(center);
    for (const u of units) {
        shift(u);
        u.subs.forEach(shift);
    }

    return {
        center,
        units,
        width: maxX - minX + 2 * MARGIN,
        height: maxY - minY + 2 * MARGIN,
    };
}

export interface Point {
    x: number;
    y: number;
}

/** Point where the ray from a circle's centre towards (tx,ty) crosses the
 * circle's border. */
export function borderPoint(c: Circle, tx: number, ty: number): Point {
    const dx = tx - c.x;
    const dy = ty - c.y;
    const dist = Math.hypot(dx, dy);
    if (dist === 0) {
        return { x: c.x, y: c.y };
    }
    return { x: c.x + (dx / dist) * c.r, y: c.y + (dy / dist) * c.r };
}

export interface EdgeGeom {
    x1: number;
    y1: number;
    x2: number;
    y2: number;
}

/** An edge that starts on circle A's border and ends on circle B's border, so
 * it visually touches both bubbles. */
export function edgeBetween(a: Circle, b: Circle): EdgeGeom {
    const start = borderPoint(a, b.x, b.y);
    const end = borderPoint(b, a.x, a.y);
    return { x1: start.x, y1: start.y, x2: end.x, y2: end.y };
}

// ---------------------------------------------------------------------------
// Prerequisite DAG (the guided-learning order)
//
// Directed arrows drawn OVER the radial map: prerequisite -> dependent. They
// mirror the same DAG the engine gates on, so what the map shows and what the
// scheduler withholds always agree.
// ---------------------------------------------------------------------------

export interface PrereqEdge {
    from: string; // prerequisite tag (arrow tail)
    to: string; // dependent tag (arrow head)
    geom: EdgeGeom;
    kind: "subtopic" | "unit";
}

/** All prerequisite arrows for the map: subtopic -> subtopic (within a unit)
 * and unit -> unit (the cross-unit order). Each runs border-to-border so it
 * visually touches both bubbles; the arrowhead sits at the dependent end. */
export function prereqEdges(layout: Layout): PrereqEdge[] {
    const leafByTag = new Map<string, LeafNode>();
    for (const u of layout.units) {
        for (const s of u.subs) {
            leafByTag.set(s.tag, s);
        }
    }
    const edges: PrereqEdge[] = [];
    for (const u of layout.units) {
        for (const s of u.subs) {
            for (const p of s.prereqs) {
                const from = leafByTag.get(p);
                if (from) {
                    edges.push({
                        from: p,
                        to: s.tag,
                        geom: edgeBetween(from, s),
                        kind: "subtopic",
                    });
                }
            }
        }
    }
    const unitById = new Map(layout.units.map((u) => [u.id, u]));
    for (const u of layout.units) {
        for (const p of UNIT_PREREQS[u.id] ?? []) {
            const from = unitById.get(p);
            if (from) {
                edges.push({
                    from: `unit::${p}`,
                    to: `unit::${u.id}`,
                    geom: edgeBetween(from, u),
                    kind: "unit",
                });
            }
        }
    }
    return edges;
}

/** Arrowhead triangle (an SVG points string) at the END of an edge, pointing
 * along the edge direction. `size` is the arrow length in px. */
export function arrowHead(geom: EdgeGeom, size = 12): string {
    const dx = geom.x2 - geom.x1;
    const dy = geom.y2 - geom.y1;
    const len = Math.hypot(dx, dy) || 1;
    const ux = dx / len;
    const uy = dy / len;
    const bx = geom.x2 - ux * size; // base, `size` back from the tip
    const by = geom.y2 - uy * size;
    const w = size * 0.5; // half-width of the base
    const px = -uy * w;
    const py = ux * w;
    return `${geom.x2},${geom.y2} ${bx + px},${by + py} ${bx - px},${by - py}`;
}

/** Map of subtopic tag -> its prerequisite tags (within its unit). */
function subtopicPrereqMap(): Map<string, string[]> {
    const m = new Map<string, string[]>();
    for (const u of TAXONOMY) {
        for (const s of u.subtopics) {
            m.set(
                subtopicTag(u.id, s.id),
                s.prereqs.map((p) => subtopicTag(u.id, p)),
            );
        }
    }
    return m;
}

/** Transitive prerequisites (ancestors — do these first) and dependents
 * (descendants — these unlock afterwards) of a subtopic tag, for highlighting a
 * selected bubble's chain on the map. Within-unit (subtopic prereqs live inside
 * a unit); cross-unit order is shown by the unit arrows. */
export function prereqChain(tag: string): {
    ancestors: Set<string>;
    descendants: Set<string>;
} {
    const prereqs = subtopicPrereqMap();
    const deps = new Map<string, string[]>();
    for (const [t, ps] of prereqs) {
        for (const p of ps) {
            (deps.get(p) ?? deps.set(p, []).get(p)!).push(t);
        }
    }
    const walk = (start: string, graph: Map<string, string[]>): Set<string> => {
        const out = new Set<string>();
        const stack = [...(graph.get(start) ?? [])];
        while (stack.length) {
            const cur = stack.pop()!;
            if (out.has(cur)) {
                continue;
            }
            out.add(cur);
            for (const n of graph.get(cur) ?? []) {
                stack.push(n);
            }
        }
        return out;
    };
    return { ancestors: walk(tag, prereqs), descendants: walk(tag, deps) };
}

// ---------------------------------------------------------------------------
// Honest mastery display
//
// These mirror the Rust gate (rslib/src/speedrun/mastery.rs) exactly so the map
// never overstates: below MIN_PROBLEMS graded reviews we have too little
// evidence to judge accuracy/retention, so we only ever show "gathering data",
// never a guessed mastery %. This is demonstrated mastery, not a predicted exam
// score (that stays behind the give-up rule in ComputeReadiness).
// ---------------------------------------------------------------------------

export const MIN_PROBLEMS = 10;
export const MIN_ACCURACY = 0.8;
export const MIN_RETRIEVABILITY = 0.9;

/** The evidence a subtopic exposes; a subset of the generated SubtopicMastery. */
export interface SubtopicEvidence {
    reviews: number;
    accuracy: number;
    meanRetrievability: number;
    gateCleared: boolean;
}

export type LeafStatus = "not_started" | "gathering" | "in_progress" | "mastered";

/** Honest status from real evidence: no accuracy claim below MIN_PROBLEMS. */
export function leafStatus(m?: SubtopicEvidence | null): LeafStatus {
    if (!m || m.reviews <= 0) {
        return "not_started";
    }
    if (m.gateCleared) {
        return "mastered";
    }
    if (m.reviews < MIN_PROBLEMS) {
        return "gathering";
    }
    return "in_progress";
}

/** Fill fraction (0..1) for a subtopic's link. Kept honest: "gathering" only
 * reflects evidence collected (capped well below the gate), and "in_progress"
 * never reaches 1 until the gate actually clears. */
export function leafProgress(m?: SubtopicEvidence | null): number {
    switch (leafStatus(m)) {
        case "not_started":
            return 0;
        case "mastered":
            return 1;
        case "gathering":
            // Only how much evidence exists yet — capped at 0.4 so thin data
            // can never look close to mastered.
            return 0.4 * Math.min(1, m!.reviews / MIN_PROBLEMS);
        case "in_progress": {
            // Enough reviews to judge: honest distance to the acc/retention gate.
            const acc = Math.min(1, m!.accuracy / MIN_ACCURACY);
            const retr = Math.min(1, m!.meanRetrievability / MIN_RETRIEVABILITY);
            return Math.min(0.92, 0.4 + 0.5 * Math.min(acc, retr));
        }
    }
}

/** Short label for a node/pill. */
export function statusLabel(m?: SubtopicEvidence | null): string {
    switch (leafStatus(m)) {
        case "not_started":
            return "not started";
        case "mastered":
            return "mastered";
        case "gathering":
            return `gathering data (${m!.reviews}/${MIN_PROBLEMS})`;
        case "in_progress":
            return "in progress";
    }
}

/** Whether there is enough evidence (>= MIN_PROBLEMS reviews) to state an
 * accuracy/retention judgement for a subtopic at all. */
export function hasEnoughEvidence(m?: SubtopicEvidence | null): boolean {
    return !!m && m.reviews >= MIN_PROBLEMS;
}

// ---------------------------------------------------------------------------
// Today's tiered study plan
//
// The engine (GetStudyPlan) returns the decks with something due today, each
// tagged with a tier. These helpers group + label them for display. Tier values
// mirror StudyMode in proto/anki/speedrun.proto so this module stays pure (no
// generated imports) and unit-testable.
// ---------------------------------------------------------------------------

export const TIER = {
    blocked: 0,
    withinUnit: 1,
    crossUnit: 2,
    allMastered: 3,
} as const;

export interface TierMeta {
    label: string;
    blurb: string;
    color: string;
}

/** Human label, one-line rationale, and colour for a tier. */
export function tierMeta(tier: number): TierMeta {
    switch (tier) {
        case TIER.blocked:
            return {
                label: "Blocked practice",
                blurb: "Drill one subtopic in isolation to build the procedure.",
                color: COLORS.amber,
            };
        case TIER.withinUnit:
            return {
                label: "Within-unit interleaving",
                blurb: "Mix a unit's confusable sub-types to train recognition.",
                color: COLORS.accent,
            };
        case TIER.crossUnit:
            return {
                label: "Cross-unit review",
                blurb: "Interleave across units for spacing.",
                color: COLORS.green,
            };
        default:
            return { label: "Review", blurb: "", color: COLORS.grey };
    }
}

export interface TieredItem {
    tier: number;
}

export interface PlanGroup<T extends TieredItem> {
    tier: number;
    meta: TierMeta;
    items: T[];
}

/** Group plan items into tier sections (blocked -> within-unit -> cross-unit),
 * dropping empty tiers. Order within a tier is preserved (the engine already
 * ranks the blocked tier by exam importance). */
export function groupPlanByTier<T extends TieredItem>(items: T[]): PlanGroup<T>[] {
    return [TIER.blocked, TIER.withinUnit, TIER.crossUnit]
        .map((tier) => ({
            tier,
            meta: tierMeta(tier),
            items: items.filter((i) => i.tier === tier),
        }))
        .filter((group) => group.items.length > 0);
}

// ---------------------------------------------------------------------------
// Exam-coverage pace
//
// The engine (GetStudyPace) reports whether the student is introducing new
// cards fast enough to cover the syllabus before their exam. paceTone is the
// pure decision (no exam date / date passed / on track / behind) so it can be
// unit-tested; the component turns it into colour + copy.
// ---------------------------------------------------------------------------

export interface PaceView {
    hasExamDate: boolean;
    daysLeft: number;
    remainingNew: number;
    currentNewPerDay: number;
    recommendedNewPerDay: number;
    projectedDaysToFinish: number;
    onTrack: boolean;
}

export type PaceTone = "none" | "past" | "ok" | "behind";

/** Which state to show the pace card in. "none" = no exam date set yet;
 * "past" = the date is behind us; otherwise on track / behind. */
export function paceTone(p: PaceView): PaceTone {
    if (!p.hasExamDate) {
        return "none";
    }
    if (p.daysLeft < 0) {
        return "past";
    }
    return p.onTrack ? "ok" : "behind";
}
