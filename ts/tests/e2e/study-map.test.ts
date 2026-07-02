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
    await expect(page.getByText("Insurance applications")).toBeVisible();

    // Tapping a subtopic opens its mastery detail (empty collection -> not started).
    await page.getByText("Order statistics").click();
    await expect(page.getByText("Graded reviews")).toBeVisible();

    await page.screenshot({ path: "out/study-map.png", fullPage: true });
});
