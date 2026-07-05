// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "./fixtures";

test("the readiness explainer documents the three signals + the give-up rule", async ({
    page,
}) => {
    // The standalone /metrics route was folded into a collapsible "How is this
    // calculated?" explainer on the Readiness page (one honesty surface, not a
    // separate tab), so the same method text is opened inline here.
    await page.goto("/readiness-dashboard");

    const explainerToggle = page.getByRole("button", {
        name: "How is this calculated?",
    });
    await expect(explainerToggle).toBeVisible({ timeout: 15000 });
    await explainerToggle.click();

    await expect(
        page.getByRole("heading", { name: "Three signals, never blended" }),
    ).toBeVisible();
    await expect(page.getByText("How the metrics work").first()).toBeVisible();

    // One section per signal, each stated as its plain question (never blended).
    await expect(
        page.getByRole("heading", { name: "Can you recall this fact right now?" }),
    ).toBeVisible();
    await expect(
        page.getByRole("heading", {
            name: "Can you solve a new, exam-style question?",
        }),
    ).toBeVisible();
    await expect(
        page.getByRole("heading", {
            name: "Would you pass today, and how sure are we?",
        }),
    ).toBeVisible();

    // Every signal names its source.
    await expect(page.getByText(/FSRS retrievability/).first()).toBeVisible();
    await expect(page.getByText(/graded multiple-choice practice tests/)).toBeVisible();
    await expect(page.getByText(/P\(pass\) model/).first()).toBeVisible();

    // The give-up rule is stated with the real thresholds from the engine.
    await expect(page.getByText(/200 graded reviews/).first()).toBeVisible();
    await expect(page.getByText(/50% weighted syllabus coverage/)).toBeVisible();
    await expect(page.getByText(/30 graded practice-test questions/).first()).toBeVisible();

    // The readiness method is shown in plain language (Wilson band + P(pass)).
    await expect(page.getByText(/95% Wilson interval/)).toBeVisible();

    // On an empty collection every signal honestly abstains (amber "Withheld"),
    // never a fabricated number.
    await expect(page.getByText(/Withheld/).first()).toBeVisible();

    await page.screenshot({ path: "out/metrics.png", fullPage: true });
});

test("a readiness card opens the how-it-works explainer inline (no separate tab)", async ({
    page,
}) => {
    await page.goto("/home");

    await expect(page.getByText("SOAP")).toBeVisible({ timeout: 15000 });

    // "How it works" is no longer a separate tab — it's folded into a collapsible
    // explainer on the Readiness page, so the tab must be gone.
    await expect(
        page.getByRole("button", { name: "How it works", exact: true }),
    ).toHaveCount(0);

    // Open the Readiness tab, then click the Memory signal card (a real button,
    // keyboard-focusable). Its accessible name starts with "Memory:".
    await page.getByRole("button", { name: "Readiness", exact: true }).click();
    const memoryCard = page.getByRole("button", { name: /^Memory:/ });
    await expect(memoryCard).toBeVisible();
    await memoryCard.click();

    // The explainer opens in place on the readiness page (no navigation away),
    // revealing the Memory section of the method.
    await expect(
        page.getByRole("heading", { name: "Can you recall this fact right now?" }),
    ).toBeVisible();
});
