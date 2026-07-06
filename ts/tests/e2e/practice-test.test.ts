// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "./fixtures";

test("centre Exam P bubble opens its mastery detail, which launches the practice test", async ({ page }) => {
    await page.goto("/home");
    await expect(page.getByRole("heading", { name: "Study map" })).toBeVisible({
        timeout: 15000,
    });

    // The centre "Exam P" bubble now opens the overall-mastery detail; its
    // "Practice test" button launches the FULL EXAM SIMULATION.
    await page.locator("button.bubble.center").click();
    await expect(page.getByRole("heading", { name: "SOA Exam P" })).toBeVisible();
    await page
        .getByRole("button", { name: "Practice test", exact: true })
        .click();

    // The intro renders without any desktop bridge (assembly happens on Start).
    await expect(
        page.getByRole("heading", { name: "Full exam simulation" }),
    ).toBeVisible();
    // Integrity: every item is drawn from a pre-built bank, nothing generated live.
    await expect(page.getByText(/pre-built bank/)).toBeVisible();
    // Honesty framing: it records real evidence and feeds the ranged Readiness.
    await expect(page.getByText(/real graded evidence/)).toBeVisible();
    // Fixed shape per the exam, shown as a spec strip: 30 questions, A-E
    // multiple choice, on a 3:00:00 countdown. No length picker (the size is
    // set by the mode, not chosen).
    await expect(page.getByText("30", { exact: true })).toBeVisible();
    await expect(page.getByText("multiple choice")).toBeVisible();
    await expect(page.getByText("03:00:00")).toBeVisible();
    await expect(page.getByText(/auto-submits at zero/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Start exam" })).toBeVisible();

    await page.screenshot({ path: "out/practice-test.png", fullPage: true });

    // "Back to map" returns to the concept map without reloading.
    await page.getByRole("button", { name: "Back to map" }).click();
    await expect(page.getByRole("heading", { name: "Study map" })).toBeVisible();
});
