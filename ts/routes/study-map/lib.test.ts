// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { describe, expect, test } from "vitest";

import type { Circle, SubtopicEvidence } from "./lib";
import {
    borderPoint,
    computeLayout,
    edgeBetween,
    groupPlanByTier,
    hasEnoughEvidence,
    leafProgress,
    leafStatus,
    MIN_PROBLEMS,
    statusLabel,
    subRadius,
    TAXONOMY,
    TIER,
    tierMeta,
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
