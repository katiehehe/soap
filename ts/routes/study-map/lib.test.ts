// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { describe, expect, test } from "vitest";

import type { Circle, PerfEvidence, SubtopicEvidence } from "./lib";
import type { PaceView } from "./lib";
import {
    arrowHead,
    borderPoint,
    computeLayout,
    edgeBetween,
    fillSegment,
    groupPlanByTier,
    hasEnoughEvidence,
    hierEdges,
    leafProgress,
    leafStatus,
    masteryInputs,
    MIN_PERF_QUESTIONS,
    MIN_PROBLEMS,
    NODE_TOUCH,
    paceTone,
    perfProgress,
    projectedFinishWeeks,
    prereqChain,
    prereqEdges,
    renderedCorner,
    renderedHalf,
    shrinkCircle,
    squircleBorderPoint,
    squircleEdgeBetween,
    statusLabel,
    subRadius,
    subtopicTag,
    TAXONOMY,
    TIER,
    tierMeta,
    TRACK_OFFSET,
    twoTrackEdges,
    UNIT_PREREQS,
    unitRadius,
    unitWeight,
} from "./lib";

const layout = computeLayout();

function allCircles(): { label: string; c: Circle }[] {
    const circles: { label: string; c: Circle }[] = [
        { label: "center", c: layout.center },
    ];
    for (const u of layout.units) {
        circles.push({ label: `unit:${u.id}`, c: u });
        for (const s of u.subs) {
            circles.push({ label: `leaf:${s.tag}`, c: s });
        }
    }
    return circles;
}

function overlaps(a: Circle, b: Circle, gap: number): boolean {
    // Two circles overlap iff the distance between their centres is less than the
    // sum of their radii. Require a gap so bubbles are visibly separated.
    return Math.hypot(a.x - b.x, a.y - b.y) < a.r + b.r + gap;
}

describe("study-map layout", () => {
    test("has the full syllabus: 3 units, 19 subtopics", () => {
        expect(layout.units).toHaveLength(3);
        const leaves = layout.units.flatMap((u) => u.subs);
        expect(leaves).toHaveLength(19);
    });

    test("no two bubbles overlap", () => {
        const circles = allCircles();
        const collisions: string[] = [];
        for (let i = 0; i < circles.length; i++) {
            for (let j = i + 1; j < circles.length; j++) {
                if (overlaps(circles[i].c, circles[j].c, 6)) {
                    collisions.push(`${circles[i].label} <> ${circles[j].label}`);
                }
            }
        }
        expect(collisions).toEqual([]);
    });

    test("every bubble fits inside the canvas", () => {
        for (const { label, c } of allCircles()) {
            expect(c.x - c.r, `${label} left`).toBeGreaterThanOrEqual(0);
            expect(c.y - c.r, `${label} top`).toBeGreaterThanOrEqual(0);
            expect(c.x + c.r, `${label} right`).toBeLessThanOrEqual(layout.width);
            expect(c.y + c.r, `${label} bottom`).toBeLessThanOrEqual(layout.height);
        }
    });

    test("every edge touches the borders of both bubbles it connects", () => {
        const onBorder = (p: { x: number; y: number }, c: Circle): boolean => {
            return Math.abs(Math.hypot(p.x - c.x, p.y - c.y) - c.r) < 0.001;
        };

        const check = (a: Circle, b: Circle, label: string) => {
            const e = edgeBetween(a, b);
            expect(
                onBorder({ x: e.x1, y: e.y1 }, a),
                `${label} start on A border`,
            ).toBe(true);
            expect(onBorder({ x: e.x2, y: e.y2 }, b), `${label} end on B border`).toBe(
                true,
            );
        };

        for (const u of layout.units) {
            check(layout.center, u, `center->${u.id}`);
            for (const s of u.subs) {
                check(u, s, `${u.id}->${s.id}`);
            }
        }
    });

    test("borderPoint lands on the circle edge for a straight target", () => {
        const c: Circle = { x: 100, y: 100, r: 20 };
        const p = borderPoint(c, 1000, 100); // straight right
        expect(p.x).toBeCloseTo(120); // x + r
        expect(p.y).toBeCloseTo(100);
    });

    test("bubble radius grows with exam-importance weight", () => {
        // size = importance: the heaviest subtopic is strictly bigger than the
        // lightest, and radius never decreases as weight rises.
        const weights = TAXONOMY.flatMap((u) => u.subtopics).map((s) => s.weight);
        const lo = Math.min(...weights);
        const hi = Math.max(...weights);
        expect(subRadius(hi)).toBeGreaterThan(subRadius(lo));
        expect(subRadius(5)).toBeGreaterThanOrEqual(subRadius(4));

        // Units: the heaviest unit (univariate) is the biggest bubble.
        const uw = Object.fromEntries(TAXONOMY.map((u) => [u.id, unitWeight(u)]));
        expect(unitRadius(uw.univariate)).toBeGreaterThan(unitRadius(uw.general));

        // The laid-out bubbles reflect this: the biggest leaf radius belongs to a
        // top-weight subtopic.
        const leaves = layout.units.flatMap((u) => u.subs);
        const biggest = leaves.reduce((a, b) => (b.r > a.r ? b : a));
        expect(biggest.weight).toBe(hi);
    });

    test("size tiers: exam node > every unit > every subtopic", () => {
        // Structural hierarchy reads at a glance: the whole-exam centre is the
        // biggest node, a unit medium, a subtopic smallest. The radius ranges are
        // built so they never overlap across tiers.
        const centre = layout.center.r;
        const unitRadii = layout.units.map((u) => u.r);
        const leafRadii = layout.units.flatMap((u) => u.subs.map((s) => s.r));
        // Central "Exam P" node is strictly the biggest bubble.
        expect(centre).toBeGreaterThan(Math.max(...unitRadii));
        // Every unit is bigger than every subtopic (tier ranges don't overlap).
        expect(Math.min(...unitRadii)).toBeGreaterThan(Math.max(...leafRadii));
    });
});

// Distance from a point to a segment (used to prove the two rails never touch).
function pointToSeg(
    px: number,
    py: number,
    s: { x1: number; y1: number; x2: number; y2: number },
): number {
    const vx = s.x2 - s.x1;
    const vy = s.y2 - s.y1;
    const wx = px - s.x1;
    const wy = py - s.y1;
    const len2 = vx * vx + vy * vy;
    let t = len2 ? (vx * wx + vy * wy) / len2 : 0;
    t = Math.max(0, Math.min(1, t));
    return Math.hypot(px - (s.x1 + t * vx), py - (s.y1 + t * vy));
}

// Minimum distance between two segments. They are parallel here, so the four
// endpoint→opposite-segment distances suffice (parallel segments can't cross).
function segSeparation(
    a: { x1: number; y1: number; x2: number; y2: number },
    b: { x1: number; y1: number; x2: number; y2: number },
): number {
    return Math.min(
        pointToSeg(a.x1, a.y1, b),
        pointToSeg(a.x2, a.y2, b),
        pointToSeg(b.x1, b.y1, a),
        pointToSeg(b.x2, b.y2, a),
    );
}

// A point lies on a bubble's RENDERED squircle border if it is on a flat side
// (|dx| or |dy| == half-width, within the straight band) or on a rounded corner
// arc (radius renderedCorner about the corner-arc centre). Mirrors the geometry
// squircleBorderPoint solves, so arrow endpoints can be checked against the drawn
// bubble edge, not the inscribed circle.
function onSquircleBorder(
    p: { x: number; y: number },
    c: Circle,
    eps = 1e-3,
): boolean {
    const half = renderedHalf(c.r);
    const cr = renderedCorner(c.r);
    const dx = Math.abs(p.x - c.x);
    const dy = Math.abs(p.y - c.y);
    const onFlatX = Math.abs(dx - half) < eps && dy <= half - cr + eps;
    const onFlatY = Math.abs(dy - half) < eps && dx <= half - cr + eps;
    const ex = dx - (half - cr);
    const ey = dy - (half - cr);
    const onArc =
        dx > half - cr - eps &&
        dy > half - cr - eps &&
        Math.abs(Math.hypot(ex, ey) - cr) < eps;
    return onFlatX || onFlatY || onArc;
}

describe("two-track edges (dual-metric connectors)", () => {
    const onBorder = (x: number, y: number, c: Circle): boolean =>
        Math.abs(Math.hypot(x - c.x, y - c.y) - c.r) < 1e-6;

    test("both tracks touch both bubbles (endpoints on each border)", () => {
        const a: Circle = { x: 0, y: 0, r: 20 };
        const b: Circle = { x: 100, y: 0, r: 25 };
        const { memory, performance } = twoTrackEdges(a, b);
        for (const seg of [memory, performance]) {
            expect(onBorder(seg.x1, seg.y1, a), "start on A border").toBe(true);
            expect(onBorder(seg.x2, seg.y2, b), "end on B border").toBe(true);
        }
    });

    test("the two tracks are offset so they never overlap each other", () => {
        const a: Circle = { x: 0, y: 0, r: 20 };
        const b: Circle = { x: 100, y: 0, r: 25 };
        const { memory, performance } = twoTrackEdges(a, b);
        // Clearly separated (the rails are 2·offset apart), never coincident.
        expect(segSeparation(memory, performance)).toBeGreaterThan(TRACK_OFFSET);
        // They are parallel: equal direction, so they can only run side by side.
        const dir = (s: { x1: number; y1: number; x2: number; y2: number }) => {
            const dx = s.x2 - s.x1;
            const dy = s.y2 - s.y1;
            const len = Math.hypot(dx, dy);
            return { ux: dx / len, uy: dy / len };
        };
        const dm = dir(memory);
        const dp = dir(performance);
        expect(dm.ux).toBeCloseTo(dp.ux);
        expect(dm.uy).toBeCloseTo(dp.uy);
    });

    test("holds for every real edge on the map (center→unit, unit→subtopic)", () => {
        const check = (a: Circle, b: Circle, label: string) => {
            const { memory, performance } = twoTrackEdges(a, b);
            for (const [name, seg] of [
                ["memory", memory],
                ["performance", performance],
            ] as const) {
                expect(onBorder(seg.x1, seg.y1, a), `${label} ${name} on A`).toBe(true);
                expect(onBorder(seg.x2, seg.y2, b), `${label} ${name} on B`).toBe(true);
            }
            // Non-overlapping and both still inside canvas-safe geometry.
            expect(
                segSeparation(memory, performance),
                `${label} rails separated`,
            ).toBeGreaterThan(0);
        };
        for (const u of layout.units) {
            check(layout.center, u, `center->${u.id}`);
            for (const s of u.subs) {
                check(u, s, `${u.id}->${s.id}`);
            }
        }
    });

    test("offset is clamped so tiny bubbles still get real chords", () => {
        // A large offset on a small bubble must not push the chord off the circle.
        const a: Circle = { x: 0, y: 0, r: 6 };
        const b: Circle = { x: 40, y: 0, r: 6 };
        const { memory, performance } = twoTrackEdges(a, b, 100);
        for (const seg of [memory, performance]) {
            expect(Number.isFinite(seg.x1) && Number.isFinite(seg.y1)).toBe(true);
            expect(onBorder(seg.x1, seg.y1, a)).toBe(true);
            expect(onBorder(seg.x2, seg.y2, b)).toBe(true);
        }
        expect(segSeparation(memory, performance)).toBeGreaterThan(0);
    });
});

// The map is a hierarchy (subtopic -> unit -> exam) and the fill must read as
// flowing UP it: each rail is oriented CHILD -> PARENT so the coloured fill
// starts at the child end and grows toward the parent. These tests lock that
// orientation + the fill-from-child-end contract in.
describe("hierarchical upward fill (child -> parent)", () => {
    // A lower child feeding an upper parent (as a subtopic feeds its unit, or a
    // unit feeds the central exam node).
    const child: Circle = { x: 0, y: 200, r: 20 };
    const parent: Circle = { x: 0, y: 0, r: 30 };
    const near = (v: number, t: number): boolean => Math.abs(v - t) < 1e-6;

    test("rails start on the child border and end on the parent border", () => {
        const { memory, performance } = hierEdges(child, parent);
        for (const seg of [memory, performance]) {
            // (x1,y1) sits on the CHILD's border...
            expect(
                near(Math.hypot(seg.x1 - child.x, seg.y1 - child.y), child.r),
            ).toBe(true);
            // ...and (x2,y2) on the PARENT's border.
            expect(
                near(Math.hypot(seg.x2 - parent.x, seg.y2 - parent.y), parent.r),
            ).toBe(true);
            // child is below the parent here, so the rail runs upward (y shrinks).
            expect(seg.y1).toBeGreaterThan(seg.y2);
        }
    });

    test("fillSegment grows FROM the child end toward the parent", () => {
        const { memory } = hierEdges(child, parent);
        // zero fill collapses to the child endpoint (nothing is drawn)
        const none = fillSegment(memory, 0);
        expect(near(none.x2, memory.x1)).toBe(true);
        expect(near(none.y2, memory.y1)).toBe(true);
        // partial fill still ORIGINATES at the child end...
        const half = fillSegment(memory, 0.5);
        expect(near(half.x1, memory.x1)).toBe(true);
        expect(near(half.y1, memory.y1)).toBe(true);
        // ...and its leading tip is halfway along the rail, i.e. it moved UP.
        expect(half.x2).toBeCloseTo((memory.x1 + memory.x2) / 2);
        expect(half.y2).toBeCloseTo((memory.y1 + memory.y2) / 2);
        expect(half.y2).toBeLessThan(memory.y1); // tip is above the child end
        // full fill spans the whole rail up to the parent border
        const full = fillSegment(memory, 1);
        expect(near(full.x2, memory.x2)).toBe(true);
        expect(near(full.y2, memory.y2)).toBe(true);
    });

    test("fill progress is clamped to [0,1] so it never overshoots the parent", () => {
        const { performance } = hierEdges(child, parent);
        const over = fillSegment(performance, 5);
        expect(near(over.x2, performance.x2)).toBe(true);
        expect(near(over.y2, performance.y2)).toBe(true);
        const under = fillSegment(performance, -3);
        expect(near(under.x2, performance.x1)).toBe(true);
        expect(near(under.y2, performance.y1)).toBe(true);
    });

    test("memory + performance stay on opposite, non-overlapping sides for any orientation", () => {
        for (const angle of [0, 30, 60, 90, 135, 180, 225, 270, 315]) {
            const rad = (angle * Math.PI) / 180;
            const c: Circle = { x: 0, y: 0, r: 18 };
            const p: Circle = {
                x: 120 * Math.cos(rad),
                y: 120 * Math.sin(rad),
                r: 24,
            };
            const { memory, performance } = hierEdges(c, p);
            expect(
                segSeparation(memory, performance),
                `angle ${angle}`,
            ).toBeGreaterThan(TRACK_OFFSET);
        }
    });

    test("every real map edge is drawn child->parent (subtopic->unit, unit->exam)", () => {
        // Mirrors +page.svelte: units feed the centre, subtopics feed their unit,
        // each rail pulled onto the visible (drawn) bubble border.
        const onDrawnBorder = (x: number, y: number, c: Circle): boolean =>
            near(Math.hypot(x - c.x, y - c.y), c.r);
        const centre = shrinkCircle(layout.center, NODE_TOUCH);
        for (const u of layout.units) {
            const uc = shrinkCircle(u, NODE_TOUCH);
            const unitToExam = hierEdges(uc, centre);
            for (const seg of [unitToExam.memory, unitToExam.performance]) {
                expect(
                    onDrawnBorder(seg.x1, seg.y1, uc),
                    `${u.id} rail starts on the unit`,
                ).toBe(true);
                expect(
                    onDrawnBorder(seg.x2, seg.y2, centre),
                    `${u.id} rail ends on the exam node`,
                ).toBe(true);
            }
            for (const s of u.subs) {
                const sc = shrinkCircle(s, NODE_TOUCH);
                const subToUnit = hierEdges(sc, uc);
                for (const seg of [subToUnit.memory, subToUnit.performance]) {
                    expect(
                        onDrawnBorder(seg.x1, seg.y1, sc),
                        `${s.id} rail starts on the subtopic`,
                    ).toBe(true);
                    expect(
                        onDrawnBorder(seg.x2, seg.y2, uc),
                        `${s.id} rail ends on the unit`,
                    ).toBe(true);
                }
            }
        }
    });
});

// The bubbles are DRAWN smaller than their collision radius (a CSS scale inset),
// so their visible border sits at NODE_TOUCH·r. Every connector endpoint AND the
// SVG bubble-mask must aim at NODE_TOUCH·r, or the line stops in the empty ring
// between the drawn bubble and the collision circle and reads as a floating gap.
// These tests lock the corrected endpoints onto the VISIBLE border.
describe("edges touch the visible (drawn) bubble border, no floating gap", () => {
    const dist = (p: { x: number; y: number }, c: Circle): number =>
        Math.hypot(p.x - c.x, p.y - c.y);
    const onVisible = (p: { x: number; y: number }, c: Circle): boolean =>
        Math.abs(dist(p, c) - c.r * NODE_TOUCH) < 1e-6;

    test("NODE_TOUCH is a real inset of the collision radius, strictly in (0,1)", () => {
        // < 1 so the endpoint sits INSIDE the collision circle (covered by the
        // drawn bubble); > 0 so the edge still reaches out from the centre.
        expect(NODE_TOUCH).toBeGreaterThan(0);
        expect(NODE_TOUCH).toBeLessThan(1);
    });

    test("shrinkCircle scales the radius and keeps the centre", () => {
        const c: Circle = { x: 12, y: -7, r: 50 };
        const s = shrinkCircle(c, NODE_TOUCH);
        expect(s.x).toBe(12);
        expect(s.y).toBe(-7);
        expect(s.r).toBeCloseTo(50 * NODE_TOUCH);
        // Identity at k=1 (the default the arrows fall back to).
        expect(shrinkCircle(c, 1)).toEqual(c);
    });

    test("both rails start/end on the VISIBLE border of every real edge", () => {
        // Mirrors what +page.svelte draws: rails between shrinkCircle(node, NODE_TOUCH).
        const check = (a: Circle, b: Circle, label: string) => {
            const { memory, performance } = twoTrackEdges(
                shrinkCircle(a, NODE_TOUCH),
                shrinkCircle(b, NODE_TOUCH),
            );
            for (const [name, seg] of [
                ["memory", memory],
                ["performance", performance],
            ] as const) {
                expect(
                    onVisible({ x: seg.x1, y: seg.y1 }, a),
                    `${label} ${name} start on A visible border`,
                ).toBe(true);
                expect(
                    onVisible({ x: seg.x2, y: seg.y2 }, b),
                    `${label} ${name} end on B visible border`,
                ).toBe(true);
            }
        };
        for (const u of layout.units) {
            check(layout.center, u, `center->${u.id}`);
            for (const s of u.subs) {
                check(u, s, `${u.id}->${s.id}`);
            }
        }
    });

    test("prereq arrows land on the drawn squircle border, tucked in the collision circle", () => {
        const leafByTag = new Map<string, Circle>(
            layout.units.flatMap((u) => u.subs.map((s) => [s.tag, s] as const)),
        );
        const unitByTag = new Map<string, Circle>(
            layout.units.map((u) => [`unit::${u.id}`, u] as const),
        );
        const nodeFor = (tag: string): Circle =>
            (leafByTag.get(tag) ?? unitByTag.get(tag))!;

        const edges = prereqEdges(layout);
        expect(edges.length).toBeGreaterThan(0);

        for (const e of edges) {
            const from = nodeFor(e.from);
            const to = nodeFor(e.to);
            // Endpoints sit on the RENDERED squircle border, so the arrowhead tip
            // touches the drawn bubble edge, no gap, nothing tucked under a corner.
            expect(
                onSquircleBorder({ x: e.geom.x1, y: e.geom.y1 }, from),
                `${e.from} tail on squircle border`,
            ).toBe(true);
            expect(
                onSquircleBorder({ x: e.geom.x2, y: e.geom.y2 }, to),
                `${e.to} head on squircle border`,
            ).toBe(true);
            // Strictly inside the collision circle → the drawn bubble covers the
            // tucked end and nothing pokes out past the bubble.
            expect(dist({ x: e.geom.x2, y: e.geom.y2 }, to)).toBeLessThan(to.r);
        }
    });
});

describe("rendered squircle border (arrow endpoints land on the drawn edge)", () => {
    const c: Circle = { x: 100, y: 100, r: 50 };
    const half = renderedHalf(c.r);
    const cr = renderedCorner(c.r);

    test("renderedHalf / renderedCorner mirror the CSS box (scale + 34%)", () => {
        expect(half).toBeCloseTo(50 * NODE_TOUCH);
        expect(cr).toBeCloseTo(0.34 * 2 * half);
        // 34% is a rounded square, not a circle (corner radius below half-width).
        expect(cr).toBeLessThan(half);
    });

    test("straight-axis rays land on the flat side at the half-width", () => {
        const right = squircleBorderPoint(c, 1000, 100);
        expect(right.x).toBeCloseTo(c.x + half);
        expect(right.y).toBeCloseTo(c.y);
        const up = squircleBorderPoint(c, 100, -1000);
        expect(up.y).toBeCloseTo(c.y - half);
        expect(up.x).toBeCloseTo(c.x);
    });

    test("a corner ray lands on the rounded arc, inside the bbox corner and the collision circle", () => {
        const p = squircleBorderPoint(c, 1000, 1000); // 45° toward the corner
        const ex = Math.abs(p.x - c.x) - (half - cr);
        const ey = Math.abs(p.y - c.y) - (half - cr);
        // On the corner arc: distance to the arc centre equals the corner radius.
        expect(Math.hypot(ex, ey)).toBeCloseTo(cr);
        const reach = Math.hypot(p.x - c.x, p.y - c.y);
        // Pulled inside the square bounding-box corner (a rounded, not sharp, corner)
        expect(reach).toBeLessThan(half * Math.SQRT2);
        // ...and inside the collision circle, so the drawn bubble covers the end.
        expect(reach).toBeLessThan(c.r);
    });

    test("squircleEdgeBetween puts both ends on each node's squircle border", () => {
        const a: Circle = { x: 0, y: 0, r: 40 };
        const b: Circle = { x: 200, y: 120, r: 55 };
        const e = squircleEdgeBetween(a, b);
        expect(onSquircleBorder({ x: e.x1, y: e.y1 }, a)).toBe(true);
        expect(onSquircleBorder({ x: e.x2, y: e.y2 }, b)).toBe(true);
    });
});

function evi(
    reviews: number,
    accuracy: number,
    meanRetrievability: number,
    gateCleared = false,
): SubtopicEvidence {
    return { reviews, accuracy, meanRetrievability, gateCleared };
}

describe("honest mastery display", () => {
    test("no data -> not started, zero progress, no accuracy claim", () => {
        expect(leafStatus(null)).toBe("not_started");
        expect(leafStatus(evi(0, 0, 0))).toBe("not_started");
        expect(leafProgress(null)).toBe(0);
        expect(statusLabel(null)).toBe("not started");
        expect(hasEnoughEvidence(null)).toBe(false);
    });

    test("thin evidence is never dressed up as mastery", () => {
        // 5 perfect reviews, but below the 10-review evidence floor: we refuse to
        // judge accuracy/retention, so this must read as "gathering data" only.
        const m = evi(5, 1.0, 1.0);
        expect(leafStatus(m)).toBe("gathering");
        expect(hasEnoughEvidence(m)).toBe(false);
        expect(statusLabel(m)).toBe(`gathering data (5/${MIN_PROBLEMS})`);
        // Even at 100% accuracy, thin data can never look close to mastered.
        expect(leafProgress(m)).toBeLessThanOrEqual(0.4);
        expect(leafProgress(m)).toBeGreaterThan(0);
    });

    test("enough reviews but gate not cleared -> in progress, never full", () => {
        const m = evi(20, 0.7, 0.85); // enough data, but under the thresholds
        expect(leafStatus(m)).toBe("in_progress");
        expect(hasEnoughEvidence(m)).toBe(true);
        expect(statusLabel(m)).toBe("in progress");
        expect(leafProgress(m)).toBeGreaterThan(0.4);
        expect(leafProgress(m)).toBeLessThan(1); // only a cleared gate reaches 1
    });

    test("cleared gate -> mastered and full", () => {
        const m = evi(15, 0.95, 0.95, true);
        expect(leafStatus(m)).toBe("mastered");
        expect(statusLabel(m)).toBe("mastered");
        expect(leafProgress(m)).toBe(1);
    });

    test("progress is monotonic: more/better evidence never lowers the fill", () => {
        const gathering = leafProgress(evi(9, 1.0, 1.0));
        const inProgress = leafProgress(evi(10, 0.9, 0.95));
        const mastered = leafProgress(evi(12, 0.95, 0.95, true));
        expect(gathering).toBeLessThan(inProgress);
        expect(inProgress).toBeLessThan(mastered);
    });
});

// The Memory rail on a map edge is filled by feeding leafProgress (its honest
// fill fraction) into fillSegment along the edge's Memory track, exactly as
// +page.svelte does. Real review evidence must produce a NON-EMPTY fill that
// grows from the child end toward the parent, on its OWN track, never shared
// with Performance. This locks the memory-edge-fill contract: a component
// reactivity bug once left every Memory rail stuck at 0 (leafProgress computed
// once against empty data, never refilled) while the Performance rails filled.
// Honest data only, built through evi()/perf(); nothing is faked to look filled.
describe("memory rail fill from review evidence (dual-metric edge)", () => {
    const child: Circle = { x: 0, y: 200, r: 20 };
    const parent: Circle = { x: 0, y: 0, r: 30 };
    const near = (v: number, t: number): boolean => Math.abs(v - t) < 1e-6;

    test("no reviews -> the Memory rail stays empty (fill collapses to the child)", () => {
        const { memory } = hierEdges(child, parent);
        const seg = fillSegment(memory, leafProgress(null));
        expect(near(seg.x2, memory.x1)).toBe(true);
        expect(near(seg.y2, memory.y1)).toBe(true);
    });

    test("real reviews drive a non-empty Memory fill that grows toward the parent", () => {
        const { memory } = hierEdges(child, parent);
        // Gathering evidence (6 real reviews) already lifts the fill off zero.
        const gathering = leafProgress(evi(6, 1.0, 1.0));
        expect(gathering).toBeGreaterThan(0);
        const seg = fillSegment(memory, gathering);
        // The fill advanced up the rail: its tip left the child end and moved
        // toward (above) the parent.
        expect(
            Math.hypot(seg.x2 - memory.x1, seg.y2 - memory.y1),
        ).toBeGreaterThan(0);
        expect(seg.y2).toBeLessThan(memory.y1);
        // A cleared memory gate fills the whole rail up to the parent border.
        const full = fillSegment(memory, leafProgress(evi(15, 0.95, 0.95, true)));
        expect(near(full.x2, memory.x2)).toBe(true);
        expect(near(full.y2, memory.y2)).toBe(true);
    });

    test("Memory and Performance rails fill from their OWN evidence, never shared", () => {
        const two = hierEdges(child, parent);
        // Memory has cleared evidence; performance has none. Only the Memory rail
        // fills (to the parent); the Performance rail stays empty at the child.
        const memFill = fillSegment(two.memory, leafProgress(evi(15, 0.95, 0.95, true)));
        const perfFill = fillSegment(two.performance, perfProgress(null));
        expect(near(memFill.x2, two.memory.x2)).toBe(true);
        expect(near(memFill.y2, two.memory.y2)).toBe(true);
        expect(near(perfFill.x2, two.performance.x1)).toBe(true);
        expect(near(perfFill.y2, two.performance.y1)).toBe(true);
    });
});

function perf(
    perfQuestions: number,
    perfCorrect: number,
    performanceMastered = false,
): PerfEvidence {
    return {
        perfQuestions,
        perfCorrect,
        perfAccuracy: perfQuestions > 0 ? perfCorrect / perfQuestions : 0,
        performanceMastered,
    };
}

describe("honest performance progress (perfProgress)", () => {
    test("no practice -> zero fill", () => {
        expect(perfProgress(null)).toBe(0);
        expect(perfProgress(perf(0, 0))).toBe(0);
    });

    test("thin practice is never dressed up as mastery (capped at 0.4)", () => {
        // Below the graded-question floor: even a perfect run stays "gathering".
        const thin = perf(MIN_PERF_QUESTIONS - 1, MIN_PERF_QUESTIONS - 1);
        expect(perfProgress(thin)).toBeLessThanOrEqual(0.4);
        expect(perfProgress(thin)).toBeGreaterThan(0);
        // A single question can never look close to mastered.
        expect(perfProgress(perf(1, 1))).toBeLessThanOrEqual(0.4);
    });

    test("enough questions but not mastered -> partial, never full", () => {
        const p = perf(10, 7); // 70% over enough questions, gate not passed
        expect(perfProgress(p)).toBeGreaterThan(0.4);
        expect(perfProgress(p)).toBeLessThan(1); // only mastery reaches full
    });

    test("mastered -> full fill", () => {
        expect(perfProgress(perf(10, 9, true))).toBe(1);
    });

    test("uncapped by time: fill reflects accumulated practice only", () => {
        // Two topics with identical practice evidence get identical fills,
        // regardless of any (absent) schedule: performance is the practice track.
        expect(perfProgress(perf(12, 10, true))).toBe(perfProgress(perf(12, 10, true)));
    });

    test("progress is monotonic: more/better practice never lowers the fill", () => {
        const thin = perfProgress(perf(MIN_PERF_QUESTIONS - 1, MIN_PERF_QUESTIONS - 1));
        const practicing = perfProgress(perf(10, 6));
        const strong = perfProgress(perf(10, 9, true));
        expect(thin).toBeLessThan(practicing);
        expect(practicing).toBeLessThan(strong);
    });
});

describe("today's tiered study plan", () => {
    test("groups items into tier sections in blocked -> within -> cross order", () => {
        const items = [
            { tier: TIER.crossUnit, id: "all" },
            { tier: TIER.blocked, id: "b1" },
            { tier: TIER.withinUnit, id: "w1" },
            { tier: TIER.blocked, id: "b2" },
        ];
        const groups = groupPlanByTier(items);
        expect(groups.map((g) => g.tier)).toEqual([
            TIER.blocked,
            TIER.withinUnit,
            TIER.crossUnit,
        ]);
        // Order within a tier is preserved (engine already ranks the blocked tier).
        expect(groups[0].items.map((i) => i.id)).toEqual(["b1", "b2"]);
        expect(groups[1].items.map((i) => i.id)).toEqual(["w1"]);
        expect(groups[2].items.map((i) => i.id)).toEqual(["all"]);
    });

    test("drops empty tiers", () => {
        const groups = groupPlanByTier([{ tier: TIER.blocked, id: "b" }]);
        expect(groups).toHaveLength(1);
        expect(groups[0].tier).toBe(TIER.blocked);
    });

    test("empty plan -> no groups (the caught-up state)", () => {
        expect(groupPlanByTier([])).toEqual([]);
    });

    test("each tier has a distinct human label", () => {
        const labels = [TIER.blocked, TIER.withinUnit, TIER.crossUnit].map(
            (t) => tierMeta(t).label,
        );
        expect(new Set(labels).size).toBe(3);
        expect(tierMeta(TIER.blocked).label).toMatch(/blocked/i);
    });
});

describe("prerequisite DAG", () => {
    test("every subtopic prereq references a real subtopic in the same unit", () => {
        for (const u of TAXONOMY) {
            const ids = new Set(u.subtopics.map((s) => s.id));
            for (const s of u.subtopics) {
                for (const p of s.prereqs) {
                    expect(ids.has(p), `${u.id}:${s.id} -> ${p}`).toBe(true);
                }
            }
        }
    });

    test("prereq edges touch both bubble borders and carry an arrowhead", () => {
        const edges = prereqEdges(layout);
        expect(edges.length).toBeGreaterThan(0);
        const leafByTag = new Map(
            layout.units.flatMap((u) => u.subs.map((s) => [s.tag, s])),
        );
        for (const e of edges.filter((e) => e.kind === "subtopic")) {
            const from = leafByTag.get(e.from)!;
            const to = leafByTag.get(e.to)!;
            // Ends land on the drawn (squircle) bubble border, tip flush on the edge.
            expect(
                onSquircleBorder({ x: e.geom.x1, y: e.geom.y1 }, from),
                `${e.from} tail`,
            ).toBe(true);
            expect(
                onSquircleBorder({ x: e.geom.x2, y: e.geom.y2 }, to),
                `${e.to} head`,
            ).toBe(true);
            // Arrowhead is a 3-point polygon whose tip sits at the edge end.
            const pts = arrowHead(e.geom).split(" ");
            expect(pts).toHaveLength(3);
            const [tx, ty] = pts[0].split(",").map(Number);
            expect(tx).toBeCloseTo(e.geom.x2);
            expect(ty).toBeCloseTo(e.geom.y2);
        }
    });

    test("unit arrows encode general -> univariate -> multivariate", () => {
        const unitEdges = prereqEdges(layout).filter((e) => e.kind === "unit");
        const pairs = unitEdges.map((e) => `${e.from}->${e.to}`);
        expect(pairs).toContain("unit::general->unit::univariate");
        expect(pairs).toContain("unit::univariate->unit::multivariate");
    });

    test("prereqChain returns ancestors to do first and dependents unlocked", () => {
        // general: sets_axioms -> add_mult_rules -> conditional -> bayes.
        const bayes = subtopicTag("general", "bayes");
        const sets = subtopicTag("general", "sets_axioms");
        const chain = prereqChain(subtopicTag("general", "conditional"));
        expect(chain.ancestors.has(sets)).toBe(true); // must be done first
        expect(chain.descendants.has(bayes)).toBe(true); // unlocks afterwards
        // A root has no ancestors.
        expect(prereqChain(sets).ancestors.size).toBe(0);
    });
});

describe("shared engine request (masteryInputs)", () => {
    test("mirrors the full taxonomy so the home probe matches the map", () => {
        const inp = masteryInputs();
        // One entry per subtopic / unit, matching the drawn map.
        expect(inp.expectedSubtopics).toHaveLength(19);
        expect(inp.subtopicWeights).toHaveLength(19);
        expect(inp.units).toHaveLength(3);
        // Tags are the canonical subtopic::unit::id form the engine gates on.
        expect(inp.expectedSubtopics).toContain(subtopicTag("general", "bayes"));
        // Unit weights are the sum of their subtopic weights.
        const general = inp.units.find((u) => u.unitId === "general")!;
        expect(general.weight).toBeCloseTo(unitWeight(TAXONOMY[0]));
    });

    test("carries the guided prerequisite DAG (cross-unit order included)", () => {
        const inp = masteryInputs();
        const multivariate = inp.unitPrereqs.find((u) => u.unitId === "multivariate")!;
        expect(multivariate.prereqs).toEqual(UNIT_PREREQS.multivariate);
        // A downstream subtopic keeps its within-unit prereq, as full tags.
        const bayes = inp.subtopicPrereqs.find(
            (s) => s.tag === subtopicTag("general", "bayes"),
        )!;
        expect(bayes.prereqs).toContain(subtopicTag("general", "conditional"));
    });
});

describe("mastery pace", () => {
    function pace(partial: Partial<PaceView>): PaceView {
        return {
            hasExamDate: true,
            daysLeft: 30,
            remainingSubtopics: 10,
            masteredSubtopics: 5,
            totalSubtopics: 19,
            daysStudied: 14,
            currentPerWeek: 2.5,
            recommendedPerWeek: 2.3,
            projectedDaysToFinish: 28,
            onTrack: true,
            ...partial,
        };
    }

    test("no exam date -> 'none' (never invent a deadline)", () => {
        expect(paceTone(pace({ hasExamDate: false }))).toBe("none");
    });

    test("past exam date -> 'past'", () => {
        expect(paceTone(pace({ daysLeft: -3 }))).toBe("past");
    });

    test("whole syllabus mastered -> 'ok' even with nothing to project", () => {
        expect(
            paceTone(pace({ remainingSubtopics: 0, projectedDaysToFinish: 0 })),
        ).toBe("ok");
    });

    test("not enough history to project -> 'gathering' (abstain, don't guess)", () => {
        expect(paceTone(pace({ projectedDaysToFinish: 0 }))).toBe("gathering");
    });

    test("on track vs behind reflects the engine's flag", () => {
        expect(paceTone(pace({ onTrack: true }))).toBe("ok");
        expect(paceTone(pace({ onTrack: false }))).toBe("behind");
    });

    test("projectedFinishWeeks rounds days to whole weeks, never below 1", () => {
        // Rounds to the nearest whole week...
        expect(projectedFinishWeeks(7)).toBe(1);
        expect(projectedFinishWeeks(10)).toBe(1); // 1.43 -> 1
        expect(projectedFinishWeeks(11)).toBe(2); // 1.57 -> 2
        expect(projectedFinishWeeks(14)).toBe(2);
        expect(projectedFinishWeeks(21)).toBe(3);
        // ...and never reads as "0 weeks" for a very near (or nonsensical) finish.
        expect(projectedFinishWeeks(0)).toBe(1);
        expect(projectedFinishWeeks(3)).toBe(1);
        expect(projectedFinishWeeks(-5)).toBe(1);
        // The 1-vs-≥2 boundary the copy pluralises on.
        expect(projectedFinishWeeks(10)).toBe(1); // "week"
        expect(projectedFinishWeeks(11)).toBeGreaterThan(1); // "weeks"
    });
});

// "Linear combos" (multivariate) is nudged up one half-width (yShiftHalfWidths:-1)
// so its Memory rail to the unit no longer passes under the neighbouring "Order
// statistics" bubble. These lock that in: the rail must clear every sibling, and
// undoing the nudge must put it back under Order statistics (so the fix can't be
// silently removed). The rail is built exactly as +page.svelte draws it: hierEdges
// on the visible (drawn) borders.
describe("Linear combos vertical nudge (memory rail clears its neighbour)", () => {
    const unit = layout.units.find((u) => u.id === "multivariate")!;
    const lc = unit.subs.find((s) => s.id === "linear_combinations")!;
    const memRail = (leaf: Circle) =>
        hierEdges(shrinkCircle(leaf, NODE_TOUCH), shrinkCircle(unit, NODE_TOUCH)).memory;

    test("its memory rail stays outside every other multivariate bubble", () => {
        const rail = memRail(lc);
        for (const s of unit.subs) {
            if (s.id === lc.id) {
                continue;
            }
            expect(pointToSeg(s.x, s.y, rail), `clears ${s.id}`).toBeGreaterThan(s.r);
        }
    });

    test("the up nudge is what clears it: un-nudged, the rail cuts under Order statistics", () => {
        const os = unit.subs.find((s) => s.id === "order_statistics")!;
        // Undo the one-half-width up nudge (it lifted Linear combos by lc.r).
        const unNudged: Circle = { x: lc.x, y: lc.y + lc.r, r: lc.r };
        expect(pointToSeg(os.x, os.y, memRail(unNudged))).toBeLessThan(os.r);
        expect(pointToSeg(os.x, os.y, memRail(lc))).toBeGreaterThan(os.r);
    });
});
