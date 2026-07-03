// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "./fixtures";

test("home shell has separate Concept map, Progress, and Readiness tabs", async ({ page }) => {
    await page.goto("/home");

    // Custom top bar (so the app does not read as stock Anki).
    await expect(page.getByText("Speedrun")).toBeVisible({ timeout: 15000 });
    const mapTab = page.getByRole("button", { name: "Concept map" });
    const progressTab = page.getByRole("button", { name: "Progress", exact: true });
    const readinessTab = page.getByRole("button", { name: "Readiness", exact: true });
    await expect(mapTab).toBeVisible();
    await expect(progressTab).toBeVisible();
    await expect(readinessTab).toBeVisible();

    // Landing tab is the concept map.
    await expect(page.getByRole("heading", { name: "Study map" })).toBeVisible();

    // Progress tab shows the plan/pace/mastery panels, NOT the readiness bundle.
    await progressTab.click();
    await expect(page.getByRole("heading", { name: "Overall mastery" })).toBeVisible();
    await expect(
        page.getByRole("heading", { name: "Exam readiness" }),
    ).not.toBeVisible();

    // Readiness tab shows the custom honesty bundle, kept separate from Anki stats.
    await readinessTab.click();
    await expect(
        page.getByRole("heading", { name: "Exam readiness" }),
    ).toBeVisible();

    // Anki's original stats live behind a clearly separate button, not a tab.
    await expect(page.getByRole("button", { name: "Anki stats" })).toBeVisible();

    await page.screenshot({ path: "out/home.png", fullPage: true });
});
