// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { describe, expect, test } from "vitest";

import { FORMULAS, formulasForTag, SOURCES } from "./formulas";

// The sheet no longer renders source citations, but traceability must stay
// re-derivable from the codebase: every curated formula keeps a NAMED source in
// the data layer. These tests lock that in so a later edit cannot quietly drop
// the provenance the honesty rule depends on.
describe("formula source provenance is retained in code", () => {
    const named: string[] = Object.values(SOURCES);

    test("the named sources are still defined", () => {
        expect(named).toContain("SOA Exam P syllabus");
        expect(named).toContain("Ross, A First Course in Probability");
        expect(named).toContain(
            "Hassett & Stewart, Probability for Risk Management",
        );
    });

    test("every formula records one of the named sources", () => {
        const all = Object.values(FORMULAS).flat();
        expect(all.length).toBeGreaterThan(0);
        for (const f of all) {
            expect(f.source).toBeTruthy();
            expect(named).toContain(f.source);
        }
    });

    test("formulasForTag still exposes sourced formulas", () => {
        const tag = Object.keys(FORMULAS)[0];
        const list = formulasForTag(tag);
        expect(list.length).toBeGreaterThan(0);
        expect(named).toContain(list[0].source);
    });
});
