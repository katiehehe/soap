// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "./fixtures";

test("home shell tabs; Anki stats is a tab, not a pop-out window", async ({ page }) => {
    await page.goto("/home");

    // Custom top bar (so the app does not read as stock Anki).
    await expect(page.getByText("Speedrun")).toBeVisible({ timeout: 15000 });

    // The task tabs, including a Stats tab (which embeds Anki's review graphs).
    for (const name of ["Map", "Readiness", "Stats"]) {
        await expect(page.getByRole("button", { name, exact: true })).toBeVisible();
    }

    // The "Practice" tab was removed from the nav — practice is launched from the
    // map instead (the centre "Exam P" bubble for the full exam, and each topic's
    // own Practice action), so it must NOT appear as a top-nav tab.
    await expect(
        page
            .getByRole("navigation", { name: "Main views" })
            .getByRole("button", { name: "Practice", exact: true }),
    ).toHaveCount(0);

    // Landing tab is the concept map.
    await expect(page.getByRole("heading", { name: "Study map" })).toBeVisible();

    // Anki's stats are no longer a separate pop-out toolbar button — they live in
    // the Stats tab now, so Anki doesn't read as a separate app. (The graphs
    // themselves are Anki's own charts; they can't render in the headless test
    // webserver, so we assert the structural change here.)
    await expect(page.getByRole("button", { name: "Anki stats" })).toHaveCount(0);

    // The "Study now" shortcut was removed from the top bar (study is launched
    // from the map's own actions instead).
    await expect(
        page.getByRole("button", { name: /Study now|Caught up/ }),
    ).toHaveCount(0);

    // Settings strip: a discoverable, two-way place for app preferences (theme,
    // tiered scheduling, AI) — replacing the old one-way "turn on AI" link.
    await page.getByRole("button", { name: "Settings", exact: true }).click();
    await expect(page.getByRole("group", { name: "Theme" })).toBeVisible();
    await expect(page.getByText("Tiered mastery scheduling")).toBeVisible();
    await expect(page.getByText("AI practice")).toBeVisible();

    await page.screenshot({ path: "out/home.png", fullPage: true });
});
