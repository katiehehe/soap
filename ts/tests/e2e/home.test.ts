// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "./fixtures";

test("home shell lands on the concept map and switches to readiness", async ({ page }) => {
    await page.goto("/home");

    // Custom top bar (so the app does not read as stock Anki).
    await expect(page.getByText("Speedrun")).toBeVisible({ timeout: 15000 });
    const mapTab = page.getByRole("button", { name: "Concept map" });
    const readinessTab = page.getByRole("button", { name: "Readiness & stats" });
    await expect(mapTab).toBeVisible();
    await expect(readinessTab).toBeVisible();

    // Landing tab is the concept map.
    await expect(page.getByRole("heading", { name: "Study map" })).toBeVisible();

    // Switching tabs shows the readiness + stats view.
    await readinessTab.click();
    await expect(
        page.getByRole("heading", { name: "Exam readiness" }),
    ).toBeVisible();

    await page.screenshot({ path: "out/home.png", fullPage: true });
});
