// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { describe, expect, test } from "vitest";

import { wilsonInterval } from "./lib";

// The TS helper mirrors wilson_interval_f in rslib/src/speedrun/service.rs, so
// the readiness dashboard's Performance band matches the engine's band math.
describe("wilsonInterval", () => {
    test("brackets the point estimate", () => {
        const { low, high } = wilsonInterval(50, 100);
        expect(low).toBeLessThan(0.5);
        expect(high).toBeGreaterThan(0.5);
        expect(low).toBeGreaterThanOrEqual(0);
        expect(high).toBeLessThanOrEqual(1);
    });

    test("zero total is degenerate (0, 0), never NaN", () => {
        expect(wilsonInterval(0, 0)).toEqual({ low: 0, high: 0 });
        const { low, high } = wilsonInterval(3, 0);
        expect(Number.isNaN(low)).toBe(false);
        expect(Number.isNaN(high)).toBe(false);
    });

    test("stays inside [0, 1] at the extremes", () => {
        const allRight = wilsonInterval(10, 10);
        expect(allRight.low).toBeGreaterThanOrEqual(0);
        expect(allRight.high).toBeLessThanOrEqual(1);
        const allWrong = wilsonInterval(0, 10);
        expect(allWrong.low).toBeGreaterThanOrEqual(0);
        expect(allWrong.high).toBeLessThanOrEqual(1);
    });

    test("smaller samples widen the interval at the same proportion", () => {
        const thin = wilsonInterval(3, 5); // p-hat 0.6, n = 5
        const thick = wilsonInterval(300, 500); // same 0.6, much more data
        expect(thin.high - thin.low).toBeGreaterThan(thick.high - thick.low);
    });

    test("matches the known Wilson band for 8/10 (z = 1.96)", () => {
        const { low, high } = wilsonInterval(8, 10);
        expect(low).toBeCloseTo(0.49, 2);
        expect(high).toBeCloseTo(0.943, 2);
    });
});
