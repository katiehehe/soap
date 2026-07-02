// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

// Pure geometry for the study-map concept map. Kept out of the Svelte component
// so the layout can be unit-tested: nodes must never overlap, every node must
// fit inside the canvas, and every edge must touch the borders of the two nodes
// it connects (no floating line ends, no gaps).

export interface SubtopicDef {
    id: string;
    name: string;
}
export interface UnitDef {
    id: string;
    name: string;
    subtopics: SubtopicDef[];
}

// Mirrors pylib/anki/speedrun/exam_p_topics.json (official 2026-05 outline).
// Names are kept short so they fit two lines inside a node box.
export const TAXONOMY: UnitDef[] = [
    {
        id: "general",
        name: "General Probability",
        subtopics: [
            { id: "sets_axioms", name: "Sets & axioms" },
            { id: "combinatorics", name: "Combinatorics" },
            { id: "independence", name: "Independence" },
            { id: "add_mult_rules", name: "Addition & mult. rules" },
            { id: "conditional", name: "Conditional prob." },
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
            { id: "discrete_dists", name: "Discrete dist." },
            { id: "continuous_dists", name: "Continuous dist." },
            { id: "insurance_apps", name: "Insurance apps" },
        ],
    },
    {
        id: "multivariate",
        name: "Multivariate RVs",
        subtopics: [
            { id: "joint_distributions", name: "Joint distributions" },
            { id: "marginal_conditional", name: "Marginal & cond." },
            { id: "joint_moments", name: "Joint moments" },
            { id: "covariance_correlation", name: "Covariance & corr." },
            { id: "order_statistics", name: "Order statistics" },
            { id: "linear_combinations", name: "Linear combos" },
            { id: "clt", name: "Central limit thm." },
        ],
    },
];

// A calmer, cohesive palette (traffic-light meaning, softened).
export const COLORS = {
    grey: "#a7b2c2", // not started
    amber: "#e0a552", // in progress
    green: "#57a37c", // mastered
    accent: "#6486bf", // the central node
};

// Node box sizes. These are also applied inline in the component so the DOM
// boxes match the geometry exactly (which is what makes the edges touch).
export const SIZE = {
    center: { w: 118, h: 50 },
    unit: { w: 152, h: 56 },
    leaf: { w: 132, h: 54 },
};

// Radial layout constants. Two rings (near/far) per unit halve the number of
// nodes competing for angular space. The inner ring must clear the unit nodes,
// and the outer ring must clear the inner ring, which is what sets the radii.
// Values verified by lib.test.ts (no overlaps, everything inside the canvas).
const R_UNIT = 190;
const R_IN = 372;
const R_OUT = 540;
const STEP_DEG = 16; // angular gap between consecutive subtopics of a unit
const UNIT_ANGLES_DEG = [-90, 30, 150]; // upward-pointing equilateral triangle
const MARGIN = 46;
const DEG = Math.PI / 180;

export interface Box {
    x: number; // centre
    y: number;
    w: number;
    h: number;
}
export interface LeafNode extends Box {
    id: string;
    name: string;
    tag: string;
    unitId: string;
}
export interface UnitNode extends Box {
    id: string;
    name: string;
    subs: LeafNode[];
}
export interface Layout {
    center: Box;
    units: UnitNode[];
    width: number;
    height: number;
}

export function subtopicTag(unitId: string, subId: string): string {
    return `subtopic::${unitId}::${subId}`;
}

/** Compute absolute node positions with the whole diagram shifted into a
 * positive, margin-padded canvas. */
export function computeLayout(): Layout {
    // 1. lay out around origin (0,0 = centre node)
    const center: Box = { x: 0, y: 0, ...SIZE.center };
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
                x: r * Math.cos(angle),
                y: r * Math.sin(angle),
                ...SIZE.leaf,
            };
        });
        return { id: u.id, name: u.name, x: ux, y: uy, ...SIZE.unit, subs };
    });

    // 2. measure bounds over every box
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    const measure = (b: Box) => {
        minX = Math.min(minX, b.x - b.w / 2);
        maxX = Math.max(maxX, b.x + b.w / 2);
        minY = Math.min(minY, b.y - b.h / 2);
        maxY = Math.max(maxY, b.y + b.h / 2);
    };
    measure(center);
    for (const u of units) {
        measure(u);
        u.subs.forEach(measure);
    }

    // 3. shift into positive space with a margin
    const dx = MARGIN - minX;
    const dy = MARGIN - minY;
    const shift = (b: Box) => {
        b.x += dx;
        b.y += dy;
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

/** Point where the ray from a box centre towards (tx,ty) crosses the box border. */
export function borderPoint(box: Box, tx: number, ty: number): Point {
    const dx = tx - box.x;
    const dy = ty - box.y;
    if (dx === 0 && dy === 0) {
        return { x: box.x, y: box.y };
    }
    const sx = dx !== 0 ? box.w / 2 / Math.abs(dx) : Infinity;
    const sy = dy !== 0 ? box.h / 2 / Math.abs(dy) : Infinity;
    const t = Math.min(sx, sy);
    return { x: box.x + dx * t, y: box.y + dy * t };
}

export interface EdgeGeom {
    x1: number;
    y1: number;
    x2: number;
    y2: number;
}

/** An edge that starts on box A's border and ends on box B's border, so it
 * visually touches both nodes. */
export function edgeBetween(a: Box, b: Box): EdgeGeom {
    const start = borderPoint(a, b.x, b.y);
    const end = borderPoint(b, a.x, a.y);
    return { x1: start.x, y1: start.y, x2: end.x, y2: end.y };
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
