// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "./fixtures";

test("readiness dashboard renders the give-up state", async ({ page }) => {
    await page.goto("/readiness-dashboard");

    // The e2e harness uses an empty collection, which is below the give-up
    // threshold, so the dashboard must show NoScore, never a fabricated number.
    // "Not enough data yet" appears in both the Readiness signal card and the
    // detail badge, so match the first occurrence.
    await expect(
        page.getByText("Not enough data yet", { exact: true }).first(),
    ).toBeVisible({ timeout: 15000 });
    await expect(page.getByText("Single best next action").first()).toBeVisible();
    await expect(page.getByText("What every readiness report must show")).toBeVisible();
    // The three signals must be shown separately, never blended into one number.
    await expect(page.getByRole("heading", { name: "Memory" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Performance" })).toBeVisible();
    await expect(
        page.getByRole("heading", { name: "Readiness" }).first(),
    ).toBeVisible();

    await page.screenshot({ path: "out/readiness-dashboard.png", fullPage: true });
});
