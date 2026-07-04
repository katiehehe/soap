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

    // Performance-first legend: the two recommendation kinds are shown. There is
    // no guided-gate toggle any more — the guided sequence is advisory arrows only,
    // never a lock (so no lock badges either).
    await expect(page.getByText(/Practice next/).first()).toBeVisible();
    await expect(page.getByText(/Review —/).first()).toBeVisible();
    await expect(page.locator(".lock-badge")).toHaveCount(0);

    // The two connector tracks are unambiguously labelled: a SOLID Memory line
    // and a DOTTED Performance line. The legend renders two swatches (one per
    // track) drawn with the same stroke/dash as the rails, and spells out the
    // solid-vs-dotted mnemonic + the upward (child → parent) fill direction.
    const trackLegend = page.locator(".track-legend");
    await expect(trackLegend.locator(".track-swatch")).toHaveCount(2);
    await expect(trackLegend.getByText("dotted")).toBeVisible();
    await expect(trackLegend.getByText(/subtopic → unit → Exam P/)).toBeVisible();

    // Overall mastery is shown, and on an empty collection it honestly reads
    // 0 of 19 mastered (a measured count, not a guess).
    await expect(page.getByRole("heading", { name: "Overall mastery" })).toBeVisible();
    await expect(page.getByText("0 / 19 subtopics")).toBeVisible();
    await expect(page.getByText("demonstrated mastery")).toBeVisible();
    // The predicted exam score is explicitly withheld (give-up rule), never faked.
    await expect(page.getByText(/projected score stays hidden/)).toBeVisible();

    // Today's plan is shown; on an empty collection nothing is due, so it
    // honestly reads the caught-up state rather than inventing decks to study.
    await expect(page.getByRole("heading", { name: "Today's plan" })).toBeVisible();
    await expect(page.getByText(/Nothing due today/)).toBeVisible();

    // Mastery pace is shown; with no exam date set it prompts for one and is
    // explicit that it's a mastery pace (subtopics clearing their gate), not a
    // predicted score.
    await expect(page.getByRole("heading", { name: "Mastery pace" })).toBeVisible();
    await expect(page.getByText(/Set your exam date/)).toBeVisible();
    await expect(page.getByText(/mastery pace/)).toBeVisible();

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
        detail.getByRole("button", { name: "Practice this topic (test)" }),
    ).toBeVisible();
    await expect(
        detail.getByRole("button", { name: "Review this topic (memory)" }),
    ).toBeVisible();

    await page.screenshot({ path: "out/study-map.png", fullPage: true });
});
