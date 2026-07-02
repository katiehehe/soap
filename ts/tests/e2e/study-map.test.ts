// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "./fixtures";

test("study map renders the three-layer topic tree", async ({ page }) => {
    await page.goto("/study-map");

    await expect(page.getByRole("heading", { name: "Study map" })).toBeVisible({
        timeout: 15000,
    });

    // The three units (layer 2 of the tree).
    await expect(page.getByText("General Probability")).toBeVisible();
    await expect(page.getByText("Univariate RVs")).toBeVisible();
    await expect(page.getByText("Multivariate RVs")).toBeVisible();

    // Some subtopics (layer 3), including the ones added to match the syllabus.
    await expect(page.getByText("Bayes' theorem")).toBeVisible();
    await expect(page.getByText("Order statistics")).toBeVisible();
    await expect(page.getByText("Insurance apps")).toBeVisible();

    // Overall mastery is shown, and on an empty collection it honestly reads
    // 0 of 19 mastered (a measured count, not a guess).
    await expect(page.getByRole("heading", { name: "Overall mastery" })).toBeVisible();
    await expect(page.getByText("0 / 19 subtopics")).toBeVisible();
    await expect(page.getByText("demonstrated mastery")).toBeVisible();
    // The predicted exam score is explicitly withheld (give-up rule), never faked.
    await expect(page.getByText(/projected score stays hidden/)).toBeVisible();

    // Tapping a subtopic opens its mastery detail (empty collection -> not started).
    await page.getByText("Order statistics").click();
    const detail = page.locator("section.detail");
    await expect(detail.getByText("Graded reviews", { exact: true })).toBeVisible();
    // With no reviews, accuracy/retention are withheld rather than guessed.
    await expect(detail.getByText(/need ≥ 10 reviews/).first()).toBeVisible();

    await page.screenshot({ path: "out/study-map.png", fullPage: true });
});
