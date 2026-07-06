// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "./fixtures";

test("study map renders the three-layer topic tree", async ({ page }) => {
    await page.goto("/study-map");

    await expect(page.getByRole("heading", { name: "Study map" })).toBeVisible({
        timeout: 15000,
    });

    // The three units (layer 2 of the tree). Unit names also appear as the
    // Memory panel's per-unit "cram" buttons on the full route, so match the
    // first occurrence (the bubble).
    await expect(page.getByText("General Probability").first()).toBeVisible();
    await expect(page.getByText("Univariate RVs").first()).toBeVisible();
    await expect(page.getByText("Multivariate RVs").first()).toBeVisible();

    // Some subtopics (layer 3), including the ones added to match the syllabus.
    await expect(page.getByText("Bayes' theorem")).toBeVisible();
    await expect(page.getByText("Order statistics")).toBeVisible();
    await expect(page.getByText("Insurance apps")).toBeVisible();

    // The map speaks ONLY in mastery colours. The colour key now lives INSIDE the
    // map as a small corner overlay (no prose caption): just each swatch paired
    // with its status label. Scope the label lookups to the key so they can't
    // match a bubble title elsewhere on the page.
    const colorKey = page.locator(".map-card .map-key");
    await expect(colorKey).toBeVisible();
    await expect(colorKey.getByText("struggling")).toBeVisible();
    await expect(colorKey.getByText("practicing")).toBeVisible();
    await expect(colorKey.getByText("strong")).toBeVisible();
    await expect(colorKey.getByText("not practiced")).toBeVisible();
    await expect(colorKey.getByText("reviewed but not yet practiced")).toBeVisible();
    // The old prose caption ("...coloured by your performance...") is gone, and the
    // old practice/review recommendation legend stays removed.
    await expect(page.getByText(/coloured by your/)).toHaveCount(0);
    await expect(page.locator(".map-legend")).toHaveCount(0);
    // The one kept map cue is the single "next" highlight on the recommended-next
    // topic; the per-node practice-glow / review-ring indicators are gone.
    await expect(page.locator(".rec-badge").first()).toBeVisible();
    // The guided sequence is advisory arrows only, never a lock (so no lock badges).
    await expect(page.locator(".lock-badge")).toHaveCount(0);

    // The two connector tracks are unambiguously labelled: a solid Memory line
    // and a dotted Performance line. The legend renders two swatches (one per
    // track) drawn with the same stroke/dash as the rails, names each signal, and
    // states the child → parent fill direction (subtopic → unit → Exam P).
    const trackLegend = page.locator(".track-legend");
    await expect(trackLegend.locator(".track-swatch")).toHaveCount(2);
    await expect(trackLegend).toContainText("Memory");
    await expect(trackLegend).toContainText("Performance");
    await expect(trackLegend.getByText(/subtopic → unit → Exam P/)).toBeVisible();

    // Overall mastery is shown, and on an empty collection it honestly reads
    // 0 of 19 mastered (a measured count, not a guess).
    await expect(page.getByRole("heading", { name: "Overall mastery" })).toBeVisible();
    await expect(page.getByText("0 / 19 subtopics")).toBeVisible();
    await expect(page.getByText("demonstrated mastery")).toBeVisible();
    // The predicted exam score is explicitly withheld (give-up rule), never faked.
    await expect(page.getByText(/projected score stays hidden/)).toBeVisible();

    // The motivating readiness banner sits at the TOP of the map. On the empty
    // e2e collection readiness is below the give-up threshold, so the banner must
    // show the honest abstain state (reason + the three gates), never a number.
    const banner = page.locator(".readiness-banner");
    await expect(banner).toBeVisible();
    await expect(banner.locator(".rb-kicker")).toContainText("not enough data yet");
    await expect(banner.getByText("Graded reviews", { exact: true })).toBeVisible();
    await expect(banner.getByText("Syllabus practiced", { exact: true })).toBeVisible();
    await expect(
        banner.getByText("Graded practice tests", { exact: true }),
    ).toBeVisible();
    // The honesty rule on the map: the full bundle is one click away in the SAME
    // view, so a score could never be shown bare. It is collapsed by default.
    await expect(banner.getByText("Point estimate")).toHaveCount(0);
    await banner
        .getByRole("button", { name: "Evidence / how this is computed" })
        .click();
    await expect(banner.getByText("Point estimate")).toBeVisible();
    await expect(banner.getByText("Likely range")).toBeVisible();

    // Today's plan is shown; on an empty collection nothing is due, so it
    // honestly reads the caught-up state rather than inventing decks to study.
    await expect(page.getByRole("heading", { name: "Today's plan" })).toBeVisible();
    await expect(page.getByText(/Caught up, nothing due today/)).toBeVisible();

    // Mastery pace is shown; with no exam date set it prompts for one and is
    // explicit that it's a mastery pace (subtopics clearing their gate), not a
    // predicted score.
    await expect(page.getByRole("heading", { name: "Mastery pace" })).toBeVisible();
    await expect(page.getByText(/Set your exam date/)).toBeVisible();
    await expect(page.getByText(/mastery pace/)).toBeVisible();

    // Bug fix (a finished session's "N due" counts went stale until a full
    // reload): the page now re-fetches its state whenever it becomes visible
    // again. A visibilitychange while the page is visible (returning to the page
    // after a review) must trigger a fresh mastery-state fetch (loadState
    // re-runs), and the page must survive it and keep rendering.
    const refetch = page.waitForRequest((r) => r.url().includes("getMasteryState"));
    await page.evaluate(() => document.dispatchEvent(new Event("visibilitychange")));
    await refetch;
    await expect(page.getByRole("heading", { name: "Study map" })).toBeVisible();

    // Clean full-map capture BEFORE opening any detail panel, so the whole
    // concept map (every cluster + its connector tracks) is visible for review.
    await page.screenshot({ path: "out/study-map-clean.png", fullPage: true });

    // Tapping a subtopic opens its mastery detail (empty collection -> not started).
    await page.getByText("Order statistics").click();
    const detail = page.locator("section.detail");
    await expect(detail.getByText("Graded reviews", { exact: true })).toBeVisible();
    // With no reviews, accuracy/retention are withheld rather than guessed.
    await expect(detail.getByText(/need ≥ 10 reviews/).first()).toBeVisible();
    // Performance is shown as its OWN signal (the spine), separate from memory.
    await expect(detail.getByText("Performance", { exact: true })).toBeVisible();
    // No gating any more: the detail offers Practice (performance) + Review (memory).
    await expect(
        detail.getByRole("button", { name: "Practice this topic" }),
    ).toBeVisible();
    await expect(
        detail.getByRole("button", { name: "Review this topic" }),
    ).toBeVisible();

    await page.screenshot({ path: "out/study-map.png", fullPage: true });
});
