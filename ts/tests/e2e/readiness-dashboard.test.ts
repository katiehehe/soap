// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "./fixtures";

test("readiness dashboard renders the give-up state", async ({ page }) => {
    await page.goto("/readiness-dashboard");

    // The e2e harness uses an empty collection, which is below the give-up
    // threshold, so the dashboard must show NoScore, never a fabricated number.
    // "Not enough data yet" is the Readiness signal card's honest value (the old
    // compact detail panel that also carried it was removed).
    await expect(
        page.getByText("Not enough data yet", { exact: true }).first(),
    ).toBeVisible({ timeout: 15000 });
    await expect(page.getByText("Single best next action").first()).toBeVisible();
    // The honesty-bundle heading and intro copy were removed, but because a
    // readiness value can be shown, every required field must still render. Assert
    // the bundle labels directly (they replace the old heading as the check).
    await expect(
        page.getByText("What every readiness report must show"),
    ).toHaveCount(0);
    await expect(page.getByText("Point estimate")).toBeVisible();
    await expect(page.getByText("Likely range")).toBeVisible();
    await expect(page.getByText("Syllabus practiced").first()).toBeVisible();
    await expect(page.getByText("How sure (confidence)")).toBeVisible();
    await expect(page.getByText("Last updated")).toBeVisible();
    await expect(page.getByText("Main reasons")).toBeVisible();
    // The three signals must be shown separately, never blended into one number.
    await expect(page.getByRole("heading", { name: "Memory" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Performance" })).toBeVisible();
    await expect(
        page.getByRole("heading", { name: "Readiness" }).first(),
    ).toBeVisible();

    // The old blending caption was removed; the three separate cards carry that
    // meaning on their own, so the sentence must no longer render.
    await expect(
        page.getByText("Three separate signals, never blended into one number."),
    ).toHaveCount(0);

    // The redundant per-card "What is this?" caption was removed; the section
    // "How is this calculated?" toggle is the single disclosure now, and each
    // card stays clickable via its aria-label, so the caption must not render.
    await expect(page.getByText("What is this?")).toHaveCount(0);
    await expect(
        page.getByRole("button", { name: "How is this calculated?" }),
    ).toBeVisible();

    await page.screenshot({ path: "out/readiness-dashboard.png", fullPage: true });
});
