// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "./fixtures";

test("study map renders the three-layer topic tree", async ({ page }) => {
    await page.goto("/study-map");

    await expect(page.getByRole("heading", { name: "Study map" })).toBeVisible({
        timeout: 15000,
    });

    // The three units (layer 2 of the tree).
    await expect(page.getByText("General Probability")).toBeVisible();
    await expect(page.getByText("Univariate RVs")).toBeVisible();
    await expect(page.getByText("Multivariate RVs")).toBeVisible();

    // Some subtopics (layer 3), including the ones added to match the syllabus.
    await expect(page.getByText("Bayes' theorem")).toBeVisible();
    await expect(page.getByText("Order statistics")).toBeVisible();
    await expect(page.getByText("Insurance apps")).toBeVisible();

    // Guided-learning DAG controls, on by default.
    await expect(page.getByText("Show prerequisites")).toBeVisible();
    await expect(page.getByText(/Guided sequence: (on|off)/)).toBeVisible();
    // On a fresh collection only the curriculum roots are open, so downstream
    // subtopics show a lock badge (the guided gate, default on).
    await expect(page.locator(".lock-badge").first()).toBeVisible();

    // Overall mastery is shown, and on an empty collection it honestly reads
    // 0 of 19 mastered (a measured count, not a guess).
    await expect(page.getByRole("heading", { name: "Overall mastery" })).toBeVisible();
    await expect(page.getByText("0 / 19 subtopics")).toBeVisible();
    await expect(page.getByText("demonstrated mastery")).toBeVisible();
    // The predicted exam score is explicitly withheld (give-up rule), never faked.
    await expect(page.getByText(/projected score stays hidden/)).toBeVisible();

    // Today's plan is shown; on an empty collection nothing is due, so it
    // honestly reads the caught-up state rather than inventing decks to study.
    await expect(page.getByRole("heading", { name: "Today's plan" })).toBeVisible();
    await expect(page.getByText(/Nothing due today/)).toBeVisible();

    // Exam pace is shown; with no exam date set it prompts for one and is
    // explicit that it's a coverage pace, not a predicted score.
    await expect(page.getByRole("heading", { name: "Exam pace" })).toBeVisible();
    await expect(page.getByText(/Set your exam date/)).toBeVisible();
    await expect(page.getByText(/coverage pace/)).toBeVisible();

    // Tapping a subtopic opens its mastery detail (empty collection -> not started).
    await page.getByText("Order statistics").click();
    const detail = page.locator("section.detail");
    await expect(detail.getByText("Graded reviews", { exact: true })).toBeVisible();
    // With no reviews, accuracy/retention are withheld rather than guessed.
    await expect(detail.getByText(/need ≥ 10 reviews/).first()).toBeVisible();
    // Performance is shown as its OWN signal, separate from the memory gate.
    await expect(detail.getByText("Performance (practice tests)")).toBeVisible();
    // Order statistics is downstream, so it's locked with a reason + a bypass.
    await expect(detail.getByText(/Locked by guided sequence/)).toBeVisible();
    await expect(detail.getByRole("button", { name: "Unlock anyway" })).toBeVisible();

    await page.screenshot({ path: "out/study-map.png", fullPage: true });
});
