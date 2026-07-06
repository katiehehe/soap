// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "./fixtures";

test("formula sheet groups formulas and searches/filters", async ({ page }) => {
    await page.goto("/formula-sheet");

    await expect(page.getByRole("heading", { name: "Formula sheet" })).toBeVisible({
        timeout: 15000,
    });

    // The "Reference only" banner and intro copy were removed, so their text is
    // gone from the page (the sheet still never moves a score).
    await expect(page.getByText(/never logs a review/)).toHaveCount(0);

    // Grouped by the official taxonomy (unit headings) with real formula names.
    await expect(
        page.getByRole("heading", { name: "General Probability" }),
    ).toBeVisible();
    await expect(
        page.locator(".formula-name", { hasText: "Bayes' theorem" }),
    ).toBeVisible();

    // Sources stay recorded in the data layer (formulas.ts) for traceability but
    // are no longer rendered on the sheet, so their named-source strings are gone.
    await expect(
        page.getByText("Ross, A First Course in Probability"),
    ).toHaveCount(0);
    await expect(
        page.getByText("Hassett & Stewart, Probability for Risk Management"),
    ).toHaveCount(0);

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
