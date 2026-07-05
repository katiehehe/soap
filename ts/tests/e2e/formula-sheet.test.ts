// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "./fixtures";

test("formula sheet groups sourced formulas and searches/filters", async ({ page }) => {
    await page.goto("/formula-sheet");

    await expect(page.getByRole("heading", { name: "Formula sheet" })).toBeVisible({
        timeout: 15000,
    });

    // Honesty: it is a reference surface and says so — it never moves a score.
    await expect(page.getByText(/never logs a review/)).toBeVisible();

    // Grouped by the official taxonomy (unit headings) with real formula names.
    await expect(
        page.getByRole("heading", { name: "General Probability" }),
    ).toBeVisible();
    await expect(
        page.locator(".formula-name", { hasText: "Bayes' theorem" }),
    ).toBeVisible();

    // Every formula names its source (SOA syllabus / Ross / Hassett & Stewart).
    await expect(
        page.getByText("Ross, A First Course in Probability").first(),
    ).toBeVisible();
    await expect(
        page.getByText("Hassett & Stewart, Probability for Risk Management").first(),
    ).toBeVisible();

    // Keyword search narrows to matching formulas only.
    await page.getByRole("textbox", { name: "Search formulas" }).fill("Poisson");
    await expect(page.getByText(/Poisson/).first()).toBeVisible();
    await expect(
        page.locator(".formula-name", { hasText: "Bayes' theorem" }),
    ).toHaveCount(0);

    // Clearing the search restores the full sheet.
    await page.getByRole("textbox", { name: "Search formulas" }).fill("");
    await expect(
        page.locator(".formula-name", { hasText: "Bayes' theorem" }),
    ).toBeVisible();

    // The unit filter scopes to one section.
    await page.getByRole("button", { name: "Multivariate RVs" }).click();
    await expect(page.getByText("Correlation coefficient")).toBeVisible();
    await expect(
        page.locator(".formula-name", { hasText: "Bayes' theorem" }),
    ).toHaveCount(0);

    await page.getByRole("button", { name: "All units" }).click();
    await expect(
        page.locator(".formula-name", { hasText: "Bayes' theorem" }),
    ).toBeVisible();

    await page.screenshot({ path: "out/formula-sheet.png", fullPage: true });
});

test("the Home shell has a Cram tab with the formula sheet", async ({ page }) => {
    await page.goto("/home");

    await expect(page.getByText("SOAP")).toBeVisible({ timeout: 15000 });

    // Memory (cram) + Formulas were merged into a single Cram tab.
    const cramTab = page.getByRole("button", { name: "Cram", exact: true });
    await expect(cramTab).toBeVisible();
    await cramTab.click();

    await expect(page.getByRole("heading", { name: "Formula sheet" })).toBeVisible();
});
