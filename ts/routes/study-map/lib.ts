// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { SIGNAL } from "../speedrun-ui/colors";

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
    // Optional per-node angular fine-tune (degrees) applied on top of the even
    // fan spacing. Used sparingly to stop a boundary spoke from clipping an inner
    // sibling (e.g. the unit→Bayes line passing under Conditional prob.).
    angleNudge?: number;
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
                // Pull slightly toward the fan centre so the unit→Bayes spoke
                // (the outer boundary node) clears this inner node instead of
                // passing under it.
                angleNudge: -5,
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
// Measured-mastery signal colours. These stay SEMANTIC (fixed meaning), sourced
// from the shared honesty palette — never rotated through the decorative accents.
export const COLORS = {
    grey: SIGNAL.pending, // not started
    amber: SIGNAL.progress, // in progress
    green: SIGNAL.mastered, // mastered / strong
    red: SIGNAL.weak, // performance: struggling
    memory: SIGNAL.memory, // memory / spaced-repetition (secondary signal)
    accent: "#8189d6", // periwinkle central node (decorative)
};

/** Total importance weight of a unit = the sum of its subtopic weights (which,
 * by construction in the topic map, equals the unit's official section
 * midpoint). */
export function unitWeight(u: UnitDef): number {
    return u.subtopics.reduce((sum, s) => sum + s.weight, 0);
}

// Bubble radii. Two things drive size, in priority order:
//   1. TIER (structural importance): the whole exam (centre) is the biggest node,
//      a unit/section is medium, a single subtopic is smallest. The three radius
//      RANGES below don't overlap (centre > every unit > every subtopic), so the
//      hierarchy always reads at a glance — verified by lib.test.ts.
//   2. WEIGHT (exam importance) WITHIN a tier: a heavier unit is a bigger bubble
//      than a lighter unit, and likewise for subtopics, so "size = importance"
//      still holds inside each tier.
// Radii stay capped well below the spacing between bubble centres (see the radial
// constants) so no two bubbles overlap — also verified by lib.test.ts.
export const CENTER_R = 82;
const UNIT_R_MIN = 60;
const UNIT_R_MAX = 70;
const SUB_R_MIN = 44;
const SUB_R_MAX = 54;

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
// largest bubbles without overlap (verified by lib.test.ts). Kept compact so
// the whole diagram fits a normal window at ~1:1 scale — the map is never shrunk
// so far that its labels turn tiny (the reason for the tightened radii here).
const R_UNIT = 198;
const R_IN = 348;
const R_OUT = 476;
const STEP_DEG = 18; // angular gap between consecutive subtopics of a unit
const UNIT_ANGLES_DEG = [-90, 30, 150]; // upward-pointing equilateral triangle
const MARGIN = 22;
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
            const angle = (base + (j - (n - 1) / 2) * STEP_DEG + (s.angleNudge ?? 0)) * DEG;
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

// ---------------------------------------------------------------------------
// Visible vs. collision radius
//
// A bubble's layout radius `r` is its COLLISION radius (used for spacing so no
// two bubbles overlap). The bubble is *rendered* smaller — `transform: scale()`
// in +page.svelte insets it — so its VISIBLE border sits at NODE_TOUCH·r. Every
// connector endpoint AND the SVG bubble-mask must aim at NODE_TOUCH·r, not the
// full r: aim at the full r and the line stops in the empty ring between the
// drawn bubble (NODE_TOUCH·r) and the collision circle (r), reading as a gap /
// "floating" edge. Keep NODE_TOUCH in sync with the CSS `scale()` on .bubble /
// .leaf so the geometry and the render agree and edges touch the bubbles.
// ---------------------------------------------------------------------------

/** Fraction of a bubble's collision radius at which its drawn border sits.
 * Mirrors the `transform: scale(0.88)` on .bubble / .leaf in +page.svelte. */
export const NODE_TOUCH = 0.88;

/** `c` at a fraction `k` of its radius (same centre). Aiming edges, arrows and
 * the bubble-mask at `shrinkCircle(node, NODE_TOUCH)` lands them on the VISIBLE
 * bubble border, so every connector touches the bubble instead of stopping in
 * the collision-radius ring around it. */
export function shrinkCircle(c: Circle, k: number): Circle {
    return { x: c.x, y: c.y, r: c.r * k };
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
// Two-track edges (the dual-metric connectors)
//
// Between two connected bubbles the map draws TWO parallel lines, one per
// signal — Memory and Performance — because there are two independent metrics
// and they must never blend into one line. Each track is a chord offset from
// the centre line by ±TRACK_OFFSET, so the two rails sit side by side and never
// overlap, while both endpoints still land exactly on the two bubble borders
// (an offset chord still meets the circle it is offset within).
// ---------------------------------------------------------------------------

/** Perpendicular half-separation (px) between the Memory and Performance rails
 * along an edge — the two tracks are 2·TRACK_OFFSET apart, so they read as two
 * clearly distinct, side-by-side lines (not a near-coincident pair) yet both
 * still touch the bubbles they connect. Stays well under the clamp in
 * `twoTrackEdges` (0.6·r of the smallest bubble ≈ 25px), so the chords remain
 * real and the endpoints stay on the border. */
export const TRACK_OFFSET = 10;

export interface TwoTrackEdges {
    /** The Memory rail (periwinkle track). */
    memory: EdgeGeom;
    /** The Performance rail (traffic-light track). */
    performance: EdgeGeom;
}

/** Two parallel border-to-border segments between circles `a` and `b`, one per
 * metric, each offset perpendicular to the a→b line by ±`offset`. Both segments
 * are chords of the two circles, so each still starts on A's border and ends on
 * B's border (touching both bubbles), while the opposite signs keep the Memory
 * and Performance rails from ever overlapping. `offset` is clamped below each
 * radius so the chords stay real for small bubbles. */
export function twoTrackEdges(
    a: Circle,
    b: Circle,
    offset: number = TRACK_OFFSET,
): TwoTrackEdges {
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const dist = Math.hypot(dx, dy) || 1;
    const ux = dx / dist; // along a→b
    const uy = dy / dist;
    const px = -uy; // perpendicular
    const py = ux;
    // Keep the chord real (and visibly inside) even for the smallest bubble.
    const d = Math.min(offset, a.r * 0.6, b.r * 0.6);
    const segFor = (s: number): EdgeGeom => {
        // Axial distance from each centre to where the offset chord crosses that
        // circle's border: sqrt(r² − s²). With the ±s perpendicular shift the
        // endpoint is exactly r from the centre, so it lands on the border.
        const aAxis = Math.sqrt(Math.max(0, a.r * a.r - s * s));
        const bAxis = Math.sqrt(Math.max(0, b.r * b.r - s * s));
        return {
            x1: a.x + ux * aAxis + px * s,
            y1: a.y + uy * aAxis + py * s,
            x2: b.x - ux * bAxis + px * s,
            y2: b.y - uy * bAxis + py * s,
        };
    };
    return { memory: segFor(d), performance: segFor(-d) };
}

// ---------------------------------------------------------------------------
// Hierarchical, upward-flowing fill (child → parent)
//
// The map is a hierarchy: subtopic leaves feed their unit, units feed the
// central "Exam P" node. The fill on each pair of rails must read as flowing UP
// that hierarchy — it originates at the CHILD end (the smaller/outer bubble) and
// grows toward the PARENT — so a student sees each child's mastery feeding into
// its parent (subtopic → unit, unit → exam). `hierEdges` fixes the orientation
// (CHILD is `a`, so both rails' (x1,y1) land on the child's border); `fillSegment`
// then grows the coloured fill from that child end. Memory keeps the +offset
// rail and Performance the −offset rail, so each signal sits on a consistent
// side of every edge.
// ---------------------------------------------------------------------------

/** Two parallel rails for a hierarchy edge, oriented CHILD → PARENT: every rail's
 * (x1,y1) lands on the CHILD's border and (x2,y2) on the PARENT's border, so a
 * fill grown from (x1,y1) flows UP from the child toward the parent (subtopic →
 * unit, unit → exam). Memory is the +offset rail, Performance the −offset rail,
 * so each signal keeps a consistent side on every edge. A thin, intent-revealing
 * wrapper over the (symmetric) `twoTrackEdges`; the argument ORDER is the
 * contract, so callers can't accidentally draw the fill flowing the wrong way. */
export function hierEdges(
    child: Circle,
    parent: Circle,
    offset: number = TRACK_OFFSET,
): TwoTrackEdges {
    return twoTrackEdges(child, parent, offset);
}

/** The filled sub-segment of a rail: it starts at the rail's CHILD end (x1,y1)
 * and extends a fraction `progress` (0..1) toward the parent end. Because a
 * hierarchy rail is oriented child → parent (see `hierEdges`), the fill always
 * grows UP from the child — the visual "this child is feeding its parent". At
 * progress 0 the segment collapses to the child endpoint (nothing drawn); at 1 it
 * spans the whole rail. `progress` is clamped to [0,1] so bad inputs can't
 * overshoot the parent bubble. */
export function fillSegment(seg: EdgeGeom, progress: number): EdgeGeom {
    const t = clamp01(progress);
    return {
        x1: seg.x1,
        y1: seg.y1,
        x2: seg.x1 + t * (seg.x2 - seg.x1),
        y2: seg.y1 + t * (seg.y2 - seg.y1),
    };
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
 * visually touches both bubbles; the arrowhead sits at the dependent end.
 * `nodeScale` shrinks both endpoints toward the VISIBLE bubble border (pass
 * NODE_TOUCH), so the arrowhead lands on the drawn bubble, not the larger
 * collision circle; the default 1 keeps the full-radius geometry. */
export function prereqEdges(layout: Layout, nodeScale = 1): PrereqEdge[] {
    const scale = (c: Circle) => shrinkCircle(c, nodeScale);
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
                        geom: edgeBetween(scale(from), scale(s)),
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
                    geom: edgeBetween(scale(from), scale(u)),
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
// Performance-first status (the spine of this app)
//
// The bubble COLOUR reflects PERFORMANCE — how well the learner solves this
// topic's exam-style problems — mirroring the Rust thresholds
// (MIN_PERF_QUESTIONS / MIN_PERF_ACCURACY in rslib/src/speedrun/mastery.rs).
// Memory (spaced repetition) is a SUPPORT signal: it only tints a bubble when
// there is no performance evidence yet, and always in a distinct (periwinkle)
// hue, so performance and memory never blend into one number.
// ---------------------------------------------------------------------------

export const MIN_PERF_QUESTIONS = 5; // mirrors rslib MIN_PERF_QUESTIONS
export const PERF_MASTERED = 0.8; // mirrors rslib MIN_PERF_ACCURACY

/** A subtopic's practice-test performance; a subset of SubtopicMastery. */
export interface PerfEvidence {
    perfQuestions: number;
    perfCorrect: number;
    perfAccuracy: number;
    performanceMastered: boolean;
}

export type PerfStatus = "untested" | "thin" | "weak" | "practicing" | "strong";

/** Honest performance status: no judgement below MIN_PERF_QUESTIONS graded
 * questions ("thin"), then weak / practicing / strong by accuracy. */
export function perfStatus(p?: PerfEvidence | null): PerfStatus {
    if (!p || p.perfQuestions <= 0) {
        return "untested";
    }
    if (p.perfQuestions < MIN_PERF_QUESTIONS) {
        return "thin";
    }
    if (p.performanceMastered) {
        return "strong";
    }
    return p.perfAccuracy >= 0.5 ? "practicing" : "weak";
}

/** Short label for a subtopic's performance. */
export function perfStatusLabel(p?: PerfEvidence | null): string {
    switch (perfStatus(p)) {
        case "untested":
            return "not practiced";
        case "thin":
            return `practicing (${p!.perfQuestions}/${MIN_PERF_QUESTIONS})`;
        case "weak":
            return "struggling";
        case "practicing":
            return "practicing";
        case "strong":
            return "strong";
    }
}

/** Traffic-light colour for a performance level. */
export function perfColor(p?: PerfEvidence | null): string {
    switch (perfStatus(p)) {
        case "strong":
            return COLORS.green;
        case "practicing":
        case "thin":
            return COLORS.amber;
        case "weak":
            return COLORS.red;
        case "untested":
            return COLORS.grey;
    }
}

/** Fill fraction (0..1) for a subtopic's PERFORMANCE track — how far practice
 * has carried this topic toward the mastery bar. Uncapped by time: it reflects
 * accumulated practice, independent of the FSRS/spaced schedule that drives the
 * Memory track. Kept honest with the same discipline as `leafProgress`: below
 * MIN_PERF_QUESTIONS graded questions we only show how much evidence exists yet
 * (capped at 0.4 so thin data can never look near-mastered), and once there is
 * enough to judge, the fill never reaches 1 until performance is actually
 * mastered. Mirrors the Rust thresholds so the map never overstates. */
export function perfProgress(p?: PerfEvidence | null): number {
    switch (perfStatus(p)) {
        case "untested":
            return 0;
        case "strong":
            return 1;
        case "thin":
            // Only how much evidence exists yet — capped at 0.4, same floor the
            // memory track uses for "gathering data".
            return 0.4 * Math.min(1, p!.perfQuestions / MIN_PERF_QUESTIONS);
        case "weak":
        case "practicing": {
            // Enough graded questions to judge: honest distance to the mastery
            // bar, never full until performance is actually mastered.
            const acc = Math.min(1, p!.perfAccuracy / PERF_MASTERED);
            return Math.min(0.92, 0.4 + 0.5 * acc);
        }
    }
}

/** Bubble colour: PERFORMANCE first; a muted MEMORY hint only when there is no
 * performance evidence yet (reviewed but not practiced → go practice); grey
 * when neither. Keeps performance primary, memory a distinct secondary cue. */
export function bubbleColor(p?: PerfEvidence | null, memReviews = 0): string {
    if (perfStatus(p) !== "untested") {
        return perfColor(p);
    }
    return memReviews > 0 ? COLORS.memory : COLORS.grey;
}

/** Scope of a practice test: one subtopic, a whole unit, or the whole exam. */
export type TestScope =
    | { kind: "all" }
    | { kind: "unit"; id: string }
    | { kind: "subtopic"; tag: string };

/** Pool a set of subtopics' performance so a unit's (or the whole exam's)
 * colour reflects how it is doing overall. */
export function rollupPerf(subs: PerfEvidence[]): PerfEvidence {
    let q = 0;
    let c = 0;
    for (const s of subs) {
        q += s.perfQuestions;
        c += s.perfCorrect;
    }
    const acc = q > 0 ? c / q : 0;
    return {
        perfQuestions: q,
        perfCorrect: c,
        perfAccuracy: acc,
        performanceMastered: q >= MIN_PERF_QUESTIONS && acc >= PERF_MASTERED,
    };
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
// Mastery pace
//
// The engine (GetStudyPace) reports how many syllabus subtopics have cleared
// their mastery gate and how fast they are clearing (observed over the study
// history), so we can say whether the student is mastering the syllabus fast
// enough for exam day — NOT just whether they have SEEN every card. paceTone is
// the pure decision (no date / date passed / not enough history yet / on track
// / behind) so it can be unit-tested; the component turns it into colour + copy.
// ---------------------------------------------------------------------------

export interface PaceView {
    hasExamDate: boolean;
    daysLeft: number;
    remainingSubtopics: number;
    masteredSubtopics: number;
    totalSubtopics: number;
    daysStudied: number;
    currentPerWeek: number;
    recommendedPerWeek: number;
    projectedDaysToFinish: number;
    onTrack: boolean;
}

export type PaceTone = "none" | "past" | "gathering" | "ok" | "behind";

/** Which state to show the pace card in. "none" = no exam date set yet; "past"
 * = the date has passed; "gathering" = a date is set but not enough is mastered
 * / not enough study history to project a finish (we abstain, never guess);
 * otherwise on track / behind. */
export function paceTone(p: PaceView): PaceTone {
    if (!p.hasExamDate) {
        return "none";
    }
    if (p.daysLeft < 0) {
        return "past";
    }
    if (p.remainingSubtopics === 0) {
        return "ok"; // whole syllabus mastered
    }
    if (p.projectedDaysToFinish <= 0) {
        return "gathering"; // not enough mastered / history to project yet
    }
    return p.onTrack ? "ok" : "behind";
}

/** Round a projected finish (in days) to whole WEEKS for display, never below 1.
 * The pace card speaks in weeks ("in about N weeks") since mastering subtopics to
 * the gate realistically spans weeks; the honest projection itself is computed in
 * days by the engine and only rounded here for readability. Always ≥ 1 so a very
 * near finish never reads as "0 weeks". */
export function projectedFinishWeeks(days: number): number {
    return Math.max(1, Math.round(days / 7));
}

// ---------------------------------------------------------------------------
// Shared engine request
//
// The taxonomy the map draws IS the taxonomy the engine gates on, so build the
// MasteryRequest inputs (weights + prerequisite DAG) once, from TAXONOMY, and
// reuse them for every RPC (get_mastery_state / get_study_plan / get_study_pace).
// Kept here so the home shell can ask "is anything due?" with the same inputs the
// map uses, without duplicating the taxonomy wiring.
// ---------------------------------------------------------------------------

export interface MasteryInputs {
    expectedSubtopics: string[];
    units: { unitId: string; weight: number }[];
    subtopicWeights: { tag: string; weight: number }[];
    subtopicPrereqs: { tag: string; prereqs: string[] }[];
    unitPrereqs: { unitId: string; prereqs: string[] }[];
}

export function masteryInputs(): MasteryInputs {
    return {
        expectedSubtopics: TAXONOMY.flatMap((u) => u.subtopics.map((s) => subtopicTag(u.id, s.id))),
        units: TAXONOMY.map((u) => ({ unitId: u.id, weight: unitWeight(u) })),
        subtopicWeights: TAXONOMY.flatMap((u) =>
            u.subtopics.map((s) => ({ tag: subtopicTag(u.id, s.id), weight: s.weight }))
        ),
        subtopicPrereqs: TAXONOMY.flatMap((u) =>
            u.subtopics.map((s) => ({
                tag: subtopicTag(u.id, s.id),
                prereqs: s.prereqs.map((p) => subtopicTag(u.id, p)),
            }))
        ),
        unitPrereqs: TAXONOMY.map((u) => ({
            unitId: u.id,
            prereqs: UNIT_PREREQS[u.id] ?? [],
        })),
    };
}
