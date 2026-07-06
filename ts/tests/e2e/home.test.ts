// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "./fixtures";

test("home shell tabs, actions, and settings strip", async ({ page }) => {
    await page.goto("/home");

    // Custom top bar (so the app does not read as stock Anki).
    await expect(page.getByText("SOAP")).toBeVisible({ timeout: 15000 });

    // Clean top-bar capture (viewport, before opening the menu) for visual review.
    await page.screenshot({ path: "out/home-topbar.png" });

    // The task tabs.
    for (const name of ["Map", "Metrics", "Stats"]) {
        await expect(page.getByRole("button", { name, exact: true })).toBeVisible();
    }

    // The "Practice" tab was removed from the nav: practice is launched from the
    // map instead (the centre "Exam P" bubble for the full exam, and each topic's
    // own Practice action), so it must NOT appear as a top-nav tab.
    await expect(
        page
            .getByRole("navigation", { name: "Main views" })
            .getByRole("button", { name: "Practice", exact: true }),
    ).toHaveCount(0);

    // Landing tab is the concept map.
    await expect(page.getByRole("heading", { name: "Study map" })).toBeVisible();

    // The "Study now" shortcut was removed from the top bar (study is launched
    // from the map's own actions instead).
    await expect(
        page.getByRole("button", { name: /Study now|Caught up/ }),
    ).toHaveCount(0);

    // On the desktop (wide) layout the secondary actions are individual, labelled
    // icon buttons: Add (+), Browse (search), Settings (gear), Sync, not a
    // hamburger. The "☰" menu is a narrow/mobile-only fallback, so it must NOT be
    // present at the default desktop viewport.
    await expect(
        page.getByRole("button", { name: "Menu", exact: true }),
    ).toHaveCount(0);
    for (const name of ["Add", "Browse", "Settings", "Sync"]) {
        await expect(
            page.getByRole("button", { name, exact: true }),
        ).toBeVisible();
    }

    // Clicking the gear (Settings) icon reveals the app-preferences strip (theme,
    // tiered scheduling, guided path, AI), a discoverable, two-way control. The
    // per-setting help text lives in `title` tooltips now, so assert the controls
    // by their accessible names (segmented group + switches) rather than inline
    // description text.
    await page.getByRole("button", { name: "Settings", exact: true }).click();
    await expect(page.getByRole("group", { name: "Theme" })).toBeVisible();
    await expect(
        page.getByRole("switch", { name: "Tiered mastery scheduling" }),
    ).toBeVisible();
    await expect(page.getByRole("switch", { name: "Guided path" })).toBeVisible();
    await expect(page.getByRole("switch", { name: "AI practice" })).toBeVisible();

    // The strip must be a SINGLE line at desktop width: the theme control and all
    // three toggles share one row, so "AI practice" never falls to a second line.
    // (Regression guard for the compact one-line layout: descriptions were moved
    // to tooltips to make room.) The controls have different heights and are
    // center-aligned, so compare their vertical CENTERS: on one flex line the
    // centers coincide (spread ~0px); a wrap puts a control a full row lower.
    const centerSpread = await page.evaluate(() => {
        const centers = [
            ...document.querySelectorAll(".settings-strip .setting"),
        ].map((el) => {
            const r = el.getBoundingClientRect();
            return r.top + r.height / 2;
        });
        return Math.max(...centers) - Math.min(...centers);
    });
    expect(centerSpread).toBeLessThan(5);

    // Capture the open settings strip so the single-line layout is reviewable.
    await page.screenshot({ path: "out/home-settings.png" });

    await page.screenshot({ path: "out/home.png", fullPage: true });
});

test("Add is an overlay that a tab click dismisses (toolbar can't freeze behind it)", async ({
    page,
}) => {
    // Regression guard for a demo-breaking freeze: the content area is a priority
    // chain ({#if addActive} … {:else if testActive} … {:else if tab === …}), so an
    // open Add screen outranks every tab. A tab click used to reset testActive but
    // NOT addActive, so once Add was open the tabs silently changed `tab`
    // underneath while Add stayed up and the toolbar looked frozen. A tab click
    // must clear the Add overlay and show that tab.
    await page.goto("/home");
    await expect(page.getByText("SOAP")).toBeVisible({ timeout: 15000 });

    // Landing tab is the concept map.
    await expect(page.getByRole("heading", { name: "Study map" })).toBeVisible();

    // Open Add via the desktop "+" icon (exact so it never matches the "Add card"
    // menu item). The categorized Add overlay takes over the content, hiding the
    // map beneath it.
    await page.getByRole("button", { name: "Add", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Add a card" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Study map" })).toHaveCount(0);

    // Click another main tab: the Add overlay must clear (addActive reset) and the
    // tab's own content must show: the toolbar is live, not wedged behind Add.
    await page.getByRole("button", { name: "Metrics", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Add a card" })).toHaveCount(0);
    await expect(
        page.getByRole("button", { name: "Metrics", exact: true }),
    ).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("button", { name: /^Readiness:/ })).toBeVisible();
});

test("narrow widths: actions collapse into a transparent-backdrop ☰ menu", async ({
    page,
}) => {
    // On phone-width viewports the Add / Browse / Settings icons collapse into the
    // top-right "☰" menu to keep the top bar compact (the desktop icon row hides).
    await page.setViewportSize({ width: 480, height: 900 });
    await page.goto("/home");
    await expect(page.getByText("SOAP")).toBeVisible({ timeout: 15000 });

    // The individual desktop icon buttons are hidden here; the "☰" is shown.
    await expect(
        page.getByRole("button", { name: "Settings", exact: true }),
    ).toHaveCount(0);
    await page.getByRole("button", { name: "Menu", exact: true }).click();

    // Menu open: the content behind must stay visible. The click-catcher backdrop
    // must be genuinely transparent, as a bare <button> otherwise inherits an opaque
    // base background and would blank the page (regression guard for the phone
    // webview, which renders this same Svelte).
    const backdropBg = await page.evaluate(
        () =>
            getComputedStyle(document.querySelector(".menu-backdrop")!)
                .backgroundColor,
    );
    expect(backdropBg).toBe("rgba(0, 0, 0, 0)");
    await page.screenshot({ path: "out/home-menu-open.png" });

    // Settings from the menu reveals the same app-preferences strip (asserted by
    // the controls' accessible names; help text lives in title tooltips now).
    await page.getByRole("menuitem", { name: "Settings", exact: true }).click();
    await expect(page.getByRole("group", { name: "Theme" })).toBeVisible();
    await expect(
        page.getByRole("switch", { name: "Tiered mastery scheduling" }),
    ).toBeVisible();
    await expect(page.getByRole("switch", { name: "Guided path" })).toBeVisible();
    await expect(page.getByRole("switch", { name: "AI practice" })).toBeVisible();
});
