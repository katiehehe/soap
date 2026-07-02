// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { describe, expect, test } from "vitest";

import type { Box, SubtopicEvidence } from "./lib";
import {
    borderPoint,
    computeLayout,
    edgeBetween,
    hasEnoughEvidence,
    leafProgress,
    leafStatus,
    MIN_PROBLEMS,
    statusLabel,
} from "./lib";

const layout = computeLayout();

function allBoxes(): { label: string; box: Box }[] {
    const boxes: { label: string; box: Box }[] = [
        { label: "center", box: layout.center },
    ];
    for (const u of layout.units) {
        boxes.push({ label: `unit:${u.id}`, box: u });
        for (const s of u.subs) {
            boxes.push({ label: `leaf:${s.tag}`, box: s });
        }
    }
    return boxes;
}

function overlaps(a: Box, b: Box, gap: number): boolean {
    // Axis-aligned boxes overlap iff they overlap on BOTH axes. Require a gap so
    // nodes are visibly separated, not just touching.
    const overlapX = Math.abs(a.x - b.x) < (a.w + b.w) / 2 + gap;
    const overlapY = Math.abs(a.y - b.y) < (a.h + b.h) / 2 + gap;
    return overlapX && overlapY;
}

describe("study-map layout", () => {
    test("has the full syllabus: 3 units, 19 subtopics", () => {
        expect(layout.units).toHaveLength(3);
        const leaves = layout.units.flatMap((u) => u.subs);
        expect(leaves).toHaveLength(19);
    });

    test("no two nodes overlap", () => {
        const boxes = allBoxes();
        const collisions: string[] = [];
        for (let i = 0; i < boxes.length; i++) {
            for (let j = i + 1; j < boxes.length; j++) {
                if (overlaps(boxes[i].box, boxes[j].box, 4)) {
                    collisions.push(`${boxes[i].label} <> ${boxes[j].label}`);
                }
            }
        }
        expect(collisions).toEqual([]);
    });

    test("every node fits inside the canvas", () => {
        for (const { label, box } of allBoxes()) {
            expect(box.x - box.w / 2, `${label} left`).toBeGreaterThanOrEqual(0);
            expect(box.y - box.h / 2, `${label} top`).toBeGreaterThanOrEqual(0);
            expect(box.x + box.w / 2, `${label} right`).toBeLessThanOrEqual(
                layout.width,
            );
            expect(box.y + box.h / 2, `${label} bottom`).toBeLessThanOrEqual(
                layout.height,
            );
        }
    });

    test("every edge touches the borders of both nodes it connects", () => {
        const onBorder = (p: { x: number; y: number }, box: Box): boolean => {
            const dx = Math.abs(p.x - box.x);
            const dy = Math.abs(p.y - box.y);
            const eps = 0.001;
            const onVertical = Math.abs(dx - box.w / 2) < eps && dy <= box.h / 2 + eps;
            const onHorizontal = Math.abs(dy - box.h / 2) < eps && dx <= box.w / 2 + eps;
            return onVertical || onHorizontal;
        };

        const check = (a: Box, b: Box, label: string) => {
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

    test("borderPoint lands on the box edge for a diagonal target", () => {
        const box: Box = { x: 100, y: 100, w: 40, h: 20 };
        const p = borderPoint(box, 1000, 100); // straight right
        expect(p.x).toBeCloseTo(120); // x + w/2
        expect(p.y).toBeCloseTo(100);
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
