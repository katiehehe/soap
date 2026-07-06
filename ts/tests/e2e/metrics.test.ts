// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "./fixtures";

test("the readiness explainer documents the three signals + the give-up rule", async ({ page }) => {
    // The standalone /metrics route was folded into a collapsible "How is this
    // calculated?" explainer on the Readiness page (one honesty surface, not a
    // separate tab), so the same method text is opened inline here. Each signal's
    // explanation is now its own tab, so only the selected signal is shown.
    await page.goto("/readiness-dashboard");

    const explainerToggle = page.getByRole("button", {
        name: "How is this calculated?",
    });
    await expect(explainerToggle).toBeVisible({ timeout: 15000 });
    await explainerToggle.click();

    // The preamble (eyebrow, h1, subtitle) and the standalone give-up callout
    // were removed so the tabs lead. Confirm the removed framing is gone; the
    // give-up rule now lives inside the Readiness tab (asserted below).
    await expect(
        page.getByRole("heading", { name: "Three signals, never blended" }),
    ).toHaveCount(0);
    await expect(page.getByText("How the metrics work")).toHaveCount(0);

    // A tablist offers the three signals; clicking one shows ONLY its explanation.
    const memoryTab = page.getByRole("tab", { name: "Memory" });
    const performanceTab = page.getByRole("tab", { name: "Performance" });
    const readinessTab = page.getByRole("tab", { name: "Readiness" });
    await expect(memoryTab).toBeVisible();
    await expect(performanceTab).toBeVisible();
    await expect(readinessTab).toBeVisible();

    // Default tab is Memory: only its panel is shown; the other two panels are
    // hidden, not stacked below.
    await expect(memoryTab).toHaveAttribute("aria-selected", "true");
    await expect(page.locator("#panel-memory")).toBeVisible();
    await expect(page.locator("#panel-performance")).toBeHidden();
    await expect(page.locator("#panel-readiness")).toBeHidden();
    await expect(
        page.getByRole("heading", { name: "Can you recall this fact right now?" }),
    ).toBeVisible();
    // The named source (FSRS retrievability) is kept in code for traceability but
    // no longer rendered inside the explainer, so it is absent from the Memory
    // panel. (The dashboard's own signal card still names it, above the panel.)
    await expect(
        page.locator("#panel-memory").getByText(/FSRS retrievability/),
    ).toHaveCount(0);
    // On an empty collection Memory honestly abstains (amber "Withheld"), never a
    // fabricated number.
    await expect(page.getByText(/Withheld/).first()).toBeVisible();

    // Clicking Performance reveals ONLY the performance panel and its detail.
    await performanceTab.click();
    await expect(performanceTab).toHaveAttribute("aria-selected", "true");
    await expect(page.locator("#panel-performance")).toBeVisible();
    await expect(page.locator("#panel-memory")).toBeHidden();
    await expect(page.locator("#panel-readiness")).toBeHidden();
    await expect(
        page.getByRole("heading", {
            name: "Can you solve a new, exam-style question?",
        }),
    ).toBeVisible();
    // Source hidden from the explainer panel; the panel still renders its detail.
    await expect(
        page
            .locator("#panel-performance")
            .getByText(/graded multiple-choice practice tests/),
    ).toHaveCount(0);
    await expect(
        page.locator("#panel-performance").getByText(/disguised, parameterized/),
    ).toBeVisible();

    // Clicking Readiness reveals ONLY the readiness panel and the plain-language
    // method (Wilson band + P(pass)).
    await readinessTab.click();
    await expect(readinessTab).toHaveAttribute("aria-selected", "true");
    await expect(page.locator("#panel-readiness")).toBeVisible();
    await expect(page.locator("#panel-memory")).toBeHidden();
    await expect(page.locator("#panel-performance")).toBeHidden();
    await expect(
        page.getByRole("heading", {
            name: "Would you pass today, and how sure are we?",
        }),
    ).toBeVisible();
    // Source hidden from the explainer panel; the plain-language method still
    // renders. (The dashboard's own readiness card still names the P(pass) model
    // above the panel, so scope the "absent" check to the panel.)
    const readinessPanel = page.locator("#panel-readiness");
    await expect(readinessPanel.getByText(/P\(pass\) model/)).toHaveCount(0);
    await expect(readinessPanel.getByText(/95% Wilson interval/)).toBeVisible();

    // The give-up rule is no longer a standalone callout: it lives in the
    // Readiness tab's own "Data thresholds (give-up rule)" block, still stating
    // the real thresholds enforced in Rust.
    // Scope to the give-up block itself (not the withheld live-note above it,
    // which also cites the review count) and confirm all three real thresholds.
    const giveUpBlock = readinessPanel
        .locator(".block")
        .filter({ hasText: "Data thresholds (give-up rule)" });
    await expect(giveUpBlock).toBeVisible();
    await expect(giveUpBlock.getByText(/200 graded reviews/)).toBeVisible();
    await expect(giveUpBlock.getByText(/50% weighted coverage/)).toBeVisible();
    // "30 graded" and "practice questions" sit either side of a source line break,
    // so assert each newline-free span rather than one string across the break.
    await expect(giveUpBlock.getByText(/30 graded/)).toBeVisible();
    await expect(giveUpBlock.getByText(/practice questions/)).toBeVisible();

    await page.screenshot({ path: "out/metrics.png", fullPage: true });
});

test("a readiness card opens the how-it-works explainer inline (no separate tab)", async ({ page }) => {
    await page.goto("/home");

    await expect(page.getByText("SOAP")).toBeVisible({ timeout: 15000 });

    // "How it works" is no longer a separate tab: it's folded into a collapsible
    // explainer on the Readiness page, so the tab must be gone.
    await expect(
        page.getByRole("button", { name: "How it works", exact: true }),
    ).toHaveCount(0);

    // Open the Readiness (Metrics) tab, then click the Readiness signal card (a
    // real button, keyboard-focusable). Its accessible name starts with
    // "Readiness:".
    await page.getByRole("button", { name: "Metrics", exact: true }).click();
    const readinessCard = page.getByRole("button", { name: /^Readiness:/ });
    await expect(readinessCard).toBeVisible();
    await readinessCard.click();

    // The explainer opens in place on the readiness page (no navigation away),
    // and the clicked signal selects its tab: the Readiness panel is shown, the
    // Memory panel is hidden.
    await expect(
        page.getByRole("tab", { name: "Readiness" }),
    ).toHaveAttribute("aria-selected", "true");
    await expect(
        page.getByRole("heading", {
            name: "Would you pass today, and how sure are we?",
        }),
    ).toBeVisible();
    await expect(page.locator("#panel-memory")).toBeHidden();

    // Clicking a different signal card switches the active tab (the anchor prop
    // drives the selection, not a scroll).
    await page.getByRole("button", { name: /^Memory:/ }).click();
    await expect(page.getByRole("tab", { name: "Memory" })).toHaveAttribute(
        "aria-selected",
        "true",
    );
    await expect(
        page.getByRole("heading", { name: "Can you recall this fact right now?" }),
    ).toBeVisible();
    await expect(page.locator("#panel-readiness")).toBeHidden();
});
