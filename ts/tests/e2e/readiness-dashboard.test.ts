// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "./fixtures";

test("readiness dashboard renders the give-up state", async ({ page }) => {
    await page.goto("/readiness-dashboard");

    // The e2e harness uses an empty collection, which is below the give-up
    // threshold, so the dashboard must show NoScore, never a fabricated number.
    await expect(
        page.getByText("Not enough data yet", { exact: true }),
    ).toBeVisible({ timeout: 15000 });
    await expect(page.getByText("Single best next action").first()).toBeVisible();
    await expect(
        page.getByText("Every readiness report must show all of this"),
    ).toBeVisible();

    await page.screenshot({ path: "out/readiness-dashboard.png", fullPage: true });
});
