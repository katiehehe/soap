<!--
Copyright: Ankitects Pty Ltd and contributors
License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
-->
<script lang="ts">
    import { onMount } from "svelte";
    import { slide } from "svelte/transition";

    import { bridgeCommand, bridgeCommandsAvailable } from "@tslib/bridgecommand";

    // The concept map, progress panels, and readiness screens are the existing
    // SvelteKit pages, reused as the tabs of the custom home shell (they still
    // work as standalone routes too). Anki's own review-history graphs are
    // embedded inline in the Stats tab, so Anki never feels like a separate app.
    import Graphs from "../graphs/+page.svelte";
    import AddCard from "../add-card/+page.svelte";
    import ConceptMap from "../study-map/+page.svelte";
    import PracticeTest from "../practice-test/+page.svelte";
    import Readiness from "../readiness-dashboard/+page.svelte";
    import FormulaSheet from "../formula-sheet/+page.svelte";
    import BrandMark from "../speedrun-ui/BrandMark.svelte";
    import type { TestScope } from "../study-map/lib";

    // Task-focused tabs: the map, the daily plan, the Memory and Readiness
    // scores, and formulas. "How it works" is folded into a collapsible panel
    // on the Readiness page rather than a separate tab. Performance practice
    // has no tab; it's launched from the map.
    type Tab = "map" | "plan" | "cram" | "readiness" | "stats";
    let tab: Tab = "map";
    // Practice-test mode is a focused overlay entered from a bubble's "Practice"
    // action: a subtopic, a unit, or the whole exam via the centre "Exam P"
    // bubble; it takes over the content area and returns to the map when done.
    // The map is the single entry point for practice (there is no Practice tab).
    let testActive = false;
    let testScope: TestScope = { kind: "all" };
    function onPracticeTest(e: CustomEvent<TestScope>): void {
        testScope = e.detail;
        testActive = true;
    }
    // Adding a card is a categorized overlay (front/back + a required subtopic),
    // not Anki's stock Add dialog; every card is filed under the syllabus.
    let addActive = false;

    // App settings shown in the collapsible settings strip: the light/dark theme,
    // the three-tier mastery scheduler (the ablation switch), and AI practice.
    // Fetched from the engine so the strip reflects the real, persisted state.
    interface Settings {
        theme: "light" | "dark";
        masteryScheduler: boolean;
        guided: boolean;
        aiEnabled: boolean;
        hasKey: boolean;
        hasPackage: boolean;
    }
    let settings: Settings = {
        theme: "light",
        masteryScheduler: true,
        guided: false,
        aiEnabled: false,
        hasKey: false,
        hasPackage: false,
    };
    let settingsOpen = false;
    // Bumping this re-mounts the concept map so a scheduler change takes effect at
    // once (the map re-reads its tier-ordered inputs) without a full page reload.
    let mapKey = 0;

    // Guarded bridge call: the Anki webview provides window.bridgeCommand, but a
    // plain browser (tests, standalone preview) does not, so never throw there.
    function send(cmd: string, cb?: (v: unknown) => void): void {
        if (bridgeCommandsAvailable()) {
            bridgeCommand(cmd, cb);
        }
    }

    onMount(() => {
        // A caller (e.g. the end-of-deck congrats screen's "Back to plan") can
        // request an initial tab via ?tab=… ; honour it if it's a real tab.
        const requested = new URLSearchParams(window.location.search).get("tab");
        const known: Tab[] = ["map", "plan", "cram", "readiness", "stats"];
        if (requested && (known as string[]).includes(requested)) {
            tab = requested as Tab;
        }
        send("speedrun-settings", (s) => {
            settings = (s as Settings) ?? settings;
        });
    });

    function setTheme(dark: boolean): void {
        settings = { ...settings, theme: dark ? "dark" : "light" };
        send("speedrun-set-theme:" + (dark ? "dark" : "light"));
    }
    function setScheduler(on: boolean): void {
        settings = { ...settings, masteryScheduler: on };
        send("speedrun-set-scheduler:" + (on ? "1" : "0"));
        mapKey += 1;
    }
    function setGuided(on: boolean): void {
        settings = { ...settings, guided: on };
        send("speedrun-set-guided:" + (on ? "1" : "0"));
        mapKey += 1;
    }
    function setAi(on: boolean): void {
        settings = { ...settings, aiEnabled: on };
        send("speedrun-set-ai-enabled:" + (on ? "1" : "0"));
    }

    // The settings strip is one compact row on desktop, so each toggle's help
    // text (and the AI "templated only" degraded state) lives in a `title`
    // tooltip instead of an inline description. aiDegraded also tints a small
    // marker so the fallback is still visible at a glance, not just on hover.
    $: aiDegraded = settings.aiEnabled && (!settings.hasKey || !settings.hasPackage);
    function aiTitleFor(s: Settings): string {
        const base = "AI practice: adds model-written, self-verified problems.";
        if (s.aiEnabled && !s.hasKey) {
            return base + " No API key; templated problems only.";
        }
        if (s.aiEnabled && !s.hasPackage) {
            return base + " openai package not installed; templated problems only.";
        }
        return base;
    }
    $: aiTitle = aiTitleFor(settings);

    // Each tab carries a muted scholarly accent used as its active colour.
    const TABS: { id: Tab; label: string; accent: string }[] = [
        { id: "map", label: "Map", accent: "var(--sr-accent)" },
        { id: "plan", label: "Plan", accent: "var(--sr-secondary)" },
        { id: "cram", label: "Cram", accent: "var(--sr-tertiary)" },
        { id: "readiness", label: "Metrics", accent: "var(--sr-quinary)" },
        { id: "stats", label: "Stats", accent: "var(--sr-accent-2)" },
    ];

    // Secondary toolbar actions. On desktop each is its own labelled icon button
    // (Add / Browse / Settings, next to Sync). On narrow/phone widths they
    // collapse into a top-right "☰" menu so the tab row stays on one line
    // (previously they wrapped the top bar onto three rows). The menu items and
    // the desktop icon buttons share the exact same handlers (onMenu / nav).
    let menuOpen = false;
    // Sync lives on the top bar as its own icon (see the header); the menu keeps
    // the rest of the secondary actions for the narrow layout.
    const MENU: { label: string; kind: "add" | "browse" | "sync" | "settings" }[] = [
        { label: "Add card", kind: "add" },
        { label: "Browse", kind: "browse" },
        { label: "Settings", kind: "settings" },
    ];

    // Desktop actions are routed to the native Anki flows through the mw.web
    // bridge handler installed by the speedrunHome state (qt/aqt/speedrun.py).
    function nav(where: string): void {
        bridgeCommand("speedrun-nav:" + where);
    }
    function onMenu(kind: string): void {
        menuOpen = false;
        if (kind === "add") {
            addActive = true;
        } else if (kind === "settings") {
            settingsOpen = !settingsOpen;
        } else {
            nav(kind);
        }
    }
</script>

<div class="app">
    <header class="topbar">
        <div class="brand">
            <span class="brand-mark"><BrandMark size={24} /></span>
            <div class="brand-text">
                <span class="brand-title">SOAP</span>
                <span class="brand-sub">SOA&nbsp;Exam&nbsp;P</span>
            </div>
        </div>

        <nav class="tabs" aria-label="Main views">
            {#each TABS as t}
                <button
                    class="tab"
                    class:active={tab === t.id}
                    style="--tab-accent:{t.accent}"
                    aria-pressed={tab === t.id}
                    on:click={() => {
                        tab = t.id;
                        testActive = false;
                        addActive = false;
                    }}
                >
                    {t.label}
                </button>
            {/each}
        </nav>

        <div class="actions">
            <!-- Desktop: each secondary action is its own labelled icon button
                 (Add / Browse / Settings), matching the Sync icon's style. On
                 narrow widths these hide and collapse into the "☰" menu below. -->
            <button
                class="icon-btn desktop-action"
                title="Add"
                aria-label="Add"
                on:click={() => onMenu("add")}
            >
                <svg
                    width="19"
                    height="19"
                    viewBox="0 0 24 24"
                    fill="none"
                    aria-hidden="true"
                >
                    <path
                        d="M12 5v14M5 12h14"
                        stroke="currentColor"
                        stroke-width="2"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                    />
                </svg>
            </button>
            <button
                class="icon-btn desktop-action"
                title="Browse"
                aria-label="Browse"
                on:click={() => onMenu("browse")}
            >
                <svg
                    width="19"
                    height="19"
                    viewBox="0 0 24 24"
                    fill="none"
                    aria-hidden="true"
                >
                    <circle
                        cx="11"
                        cy="11"
                        r="7"
                        stroke="currentColor"
                        stroke-width="2"
                    />
                    <path
                        d="M21 21l-4.35-4.35"
                        stroke="currentColor"
                        stroke-width="2"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                    />
                </svg>
            </button>
            <button
                class="icon-btn desktop-action"
                class:active={settingsOpen}
                title="Settings"
                aria-label="Settings"
                aria-pressed={settingsOpen}
                on:click={() => onMenu("settings")}
            >
                <svg
                    width="19"
                    height="19"
                    viewBox="0 0 24 24"
                    fill="none"
                    aria-hidden="true"
                >
                    <circle
                        cx="12"
                        cy="12"
                        r="3"
                        stroke="currentColor"
                        stroke-width="2"
                    />
                    <path
                        d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"
                        stroke="currentColor"
                        stroke-width="2"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                    />
                </svg>
            </button>

            <button
                class="icon-btn"
                title="Sync"
                aria-label="Sync"
                on:click={() => nav("sync")}
            >
                <svg
                    width="19"
                    height="19"
                    viewBox="0 0 24 24"
                    fill="none"
                    aria-hidden="true"
                >
                    <path
                        d="M23 4v6h-6M1 20v-6h6"
                        stroke="currentColor"
                        stroke-width="2"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                    />
                    <path
                        d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"
                        stroke="currentColor"
                        stroke-width="2"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                    />
                </svg>
            </button>

            <!-- Narrow/mobile only: the "☰" collapses Add / Browse / Settings to
                 save horizontal space. Hidden on desktop (see .mobile-menu-btn). -->
            <button
                class="menu-btn mobile-menu-btn"
                class:active={menuOpen}
                title="Menu"
                aria-label="Menu"
                aria-haspopup="true"
                aria-expanded={menuOpen}
                on:click={() => (menuOpen = !menuOpen)}
            >
                <svg
                    width="18"
                    height="14"
                    viewBox="0 0 18 14"
                    fill="none"
                    aria-hidden="true"
                >
                    <path
                        d="M1 1h16M1 7h16M1 13h16"
                        stroke="currentColor"
                        stroke-width="2"
                        stroke-linecap="round"
                    />
                </svg>
            </button>

            {#if menuOpen}
                <button
                    class="menu-backdrop"
                    aria-label="Close menu"
                    on:click={() => (menuOpen = false)}
                ></button>
                <div class="menu" role="menu" transition:slide={{ duration: 140 }}>
                    {#each MENU as m}
                        <button
                            class="menu-item"
                            class:on={m.kind === "settings" && settingsOpen}
                            role="menuitem"
                            on:click={() => onMenu(m.kind)}
                        >
                            {m.label}
                        </button>
                    {/each}
                </div>
            {/if}
        </div>
    </header>

    {#if settingsOpen}
        <div class="settings-strip" transition:slide={{ duration: 160 }}>
            <div class="setting">
                <span class="setting-label">Theme</span>
                <div class="seg" role="group" aria-label="Theme">
                    <button
                        class="seg-opt"
                        class:on={settings.theme === "light"}
                        on:click={() => setTheme(false)}
                    >
                        Light
                    </button>
                    <button
                        class="seg-opt"
                        class:on={settings.theme === "dark"}
                        on:click={() => setTheme(true)}
                    >
                        Dark
                    </button>
                </div>
            </div>

            <div
                class="setting"
                title="Tiered mastery scheduling: block → interleave, with a mastery gate. Off = plain review order (the ablation)."
            >
                <span class="setting-label">Tiered scheduling</span>
                <button
                    class="switch"
                    class:on={settings.masteryScheduler}
                    role="switch"
                    aria-checked={settings.masteryScheduler}
                    aria-label="Tiered mastery scheduling"
                    on:click={() => setScheduler(!settings.masteryScheduler)}
                >
                    <span class="knob"></span>
                </button>
            </div>

            <div
                class="setting"
                title="Guided path: walk the syllabus in order; holds a topic until its prerequisites are practiced. Off = free choice."
            >
                <span class="setting-label">Guided path</span>
                <button
                    class="switch"
                    class:on={settings.guided}
                    role="switch"
                    aria-checked={settings.guided}
                    aria-label="Guided path"
                    on:click={() => setGuided(!settings.guided)}
                >
                    <span class="knob"></span>
                </button>
            </div>

            <div class="setting" title={aiTitle}>
                <span class="setting-label">AI practice</span>
                {#if aiDegraded}
                    <span class="warn-flag" title={aiTitle} aria-hidden="true">⚠</span>
                {/if}
                <button
                    class="switch"
                    class:on={settings.aiEnabled}
                    role="switch"
                    aria-checked={settings.aiEnabled}
                    aria-label="AI practice"
                    on:click={() => setAi(!settings.aiEnabled)}
                >
                    <span class="knob"></span>
                </button>
            </div>
        </div>
    {/if}

    <main class="content">
        {#if addActive}
            <AddCard on:done={() => (addActive = false)} />
        {:else if testActive}
            <PracticeTest scope={testScope} on:done={() => (testActive = false)} />
        {:else if tab === "map"}
            {#key mapKey}
                <ConceptMap
                    variant="map"
                    masteryScheduler={settings.masteryScheduler}
                    on:practicetest={onPracticeTest}
                />
            {/key}
        {:else if tab === "plan"}
            {#key mapKey}
                <ConceptMap
                    variant="plan"
                    masteryScheduler={settings.masteryScheduler}
                    on:practicetest={onPracticeTest}
                />
            {/key}
        {:else if tab === "cram"}
            {#key mapKey}
                <ConceptMap
                    variant="cram"
                    masteryScheduler={settings.masteryScheduler}
                    on:practicetest={onPracticeTest}
                />
            {/key}
            <FormulaSheet />
        {:else if tab === "stats"}
            <div class="anki-graphs">
                <Graphs />
            </div>
        {:else}
            <Readiness />
        {/if}
    </main>
</div>

<style>
    :global(html),
    :global(body) {
        margin: 0;
        height: 100%;
    }

    .app {
        /* Palette + type come from the global theme (ts/routes/base.scss) so the
           shell + concept map + readiness read as one calm, scholarly product. */
        position: relative;
        isolation: isolate;
        display: flex;
        flex-direction: column;
        height: 100vh;
        color: var(--fg);
        background:
            radial-gradient(
                120% 80% at 50% -12%,
                var(--sr-accent-weak),
                transparent 60%
            ),
            var(--canvas);
        font-family: var(--sr-font-body);
    }
    /* Faint drifting soap bubbles: thin rings (not filled dots) tinted to the
       theme accent, so they're pale blue in light mode and teal in dark. Very
       subtle, so body text stays perfectly readable. */
    .app::before {
        content: "";
        position: absolute;
        inset: 0;
        background-image:
            radial-gradient(
                circle at 30% 32%,
                transparent 0 7px,
                var(--sr-accent-weak) 8px 9px,
                transparent 10px
            ),
            radial-gradient(
                circle at 72% 60%,
                transparent 0 11px,
                var(--sr-accent-weak) 12px 13px,
                transparent 14px
            ),
            radial-gradient(
                circle at 52% 86%,
                transparent 0 5px,
                var(--sr-accent-weak) 6px 7px,
                transparent 8px
            );
        background-size:
            150px 150px,
            220px 220px,
            120px 120px;
        pointer-events: none;
        z-index: 0;
    }

    /* Top bar, a distinct surface so it's obvious where the bar ends: an
       elevated fill (a touch different from the content canvas) plus a hairline
       bottom border and a soft shadow. */
    .topbar {
        position: sticky;
        top: 0;
        z-index: 50;
        flex: 0 0 auto;
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 0.75rem 1rem;
        padding: 0.7rem 1.5rem;
        background: var(--canvas-elevated);
        border-bottom: 1px solid var(--border);
        box-shadow: var(--sr-shadow-sm);
    }
    .brand {
        display: flex;
        align-items: center;
        gap: 0.6rem;
        /* Equal-width flank so the centered tabs sit at true viewport center. */
        flex: 1 1 0;
        min-width: 0;
    }
    .brand-mark {
        display: grid;
        place-items: center;
        width: 40px;
        height: 40px;
        border-radius: var(--sr-radius);
        background: linear-gradient(135deg, var(--sr-accent), var(--sr-accent-2));
        color: var(--sr-on-accent);
        font-family: var(--sr-font-heading);
        font-weight: 800;
        font-size: 1.15rem;
        box-shadow: var(--sr-shadow-sm);
    }
    .brand-text {
        display: flex;
        flex-direction: column;
        line-height: 1.05;
        gap: 0.1rem;
    }
    .brand-title {
        font-family: var(--sr-font-heading);
        font-weight: 700;
        font-size: 1.4rem;
        letter-spacing: 0.02em;
    }
    .brand-sub {
        font-size: 0.62rem;
        font-weight: 700;
        letter-spacing: 0.22em;
        text-transform: uppercase;
        color: var(--fg-subtle);
    }

    .tabs {
        display: flex;
        align-items: center;
        gap: 0.25rem;
        /* No auto margins: the equal-width brand/actions flanks center this. */
        margin: 0;
        flex: 0 0 auto;
        /* No container fill/border/pill: the tabs sit directly on the top bar.
           The selected view is shown per-tab (accent pill), not by this box. */
        /* Fixed row height so a tab's hover scale (a transform) overflows
           visually without ever resizing the row; the bar can't shift. */
        box-sizing: border-box;
        height: 2.85rem;
    }
    .tab {
        /* A visible hairline outline so each tab clearly reads as a button (the
           old transparent border was invisible, especially on mobile). */
        border: 1px solid color-mix(in srgb, var(--fg) 18%, transparent);
        background: transparent;
        font-family: var(--sr-font-body);
        font-weight: 700;
        font-size: 0.82rem;
        color: var(--fg-subtle);
        padding: 0.5rem 1.15rem;
        border-radius: var(--sr-radius-pill);
        cursor: pointer;
        transform-origin: center;
        /* Hover only scales the button: a transform changes its painted size, not
           the bar's layout, so the top bar never shifts up/down. */
        transition:
            transform 0.15s ease,
            background 0.2s ease,
            color 0.2s ease;
    }
    .tab:hover {
        color: var(--fg);
        border-color: color-mix(in srgb, var(--fg) 34%, transparent);
        transform: scale(1.05);
    }
    .tab:active {
        transform: scale(0.97);
    }
    .tab.active {
        color: var(--tab-accent);
        /* The active view reads as an accent-tinted pill with a clear accent ring. */
        background: color-mix(in srgb, var(--tab-accent) 16%, transparent);
        border-color: color-mix(in srgb, var(--tab-accent) 55%, transparent);
    }
    .tab:focus-visible {
        outline: 2px solid var(--sr-focus);
        outline-offset: 2px;
    }

    .actions {
        position: relative;
        display: flex;
        align-items: center;
        gap: 0.45rem;
        /* Equal-width flank, right-aligned, so the tabs stay centered. */
        flex: 1 1 0;
        min-width: 0;
        justify-content: flex-end;
    }
    /* Top-bar icon buttons: the Add / Browse / Settings / Sync symbols + the
       "☰" menu button. One shared style so the row reads as a cohesive set. */
    .menu-btn,
    .icon-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 40px;
        height: 40px;
        border: 1px solid color-mix(in srgb, var(--fg) 22%, transparent);
        background: var(--canvas-elevated);
        color: var(--fg);
        border-radius: var(--sr-radius-sm);
        cursor: pointer;
        transition:
            border-color 0.2s ease,
            color 0.2s ease,
            background 0.2s ease;
    }
    /* The "☰" is a narrow-width fallback only; on desktop the individual icon
       buttons replace it. (Declared after the base rule so it wins on ties.) */
    .mobile-menu-btn {
        display: none;
    }
    .menu-btn:hover,
    .menu-btn.active,
    .icon-btn:hover,
    .icon-btn.active {
        border-color: var(--sr-accent);
        color: var(--sr-accent);
        background: var(--sr-accent-weak);
    }
    .menu-btn:focus-visible,
    .icon-btn:focus-visible {
        outline: 2px solid var(--sr-focus);
        outline-offset: 2px;
    }
    /* Invisible full-screen catcher so a click anywhere closes the menu. The
       global `button:not(.btn, .btn-close)` base style (ts/lib/sass/base.scss)
       gives every bare <button> an OPAQUE background and outranks this class, so
       without the !important the backdrop would render opaque and blank the whole
       page whenever the menu is open (on desktop AND the phone webview). */
    .menu-backdrop {
        position: fixed;
        inset: 0;
        z-index: 55;
        margin: 0;
        padding: 0;
        border: none;
        border-radius: 0;
        background: transparent !important;
        box-shadow: none;
        cursor: default;
        -webkit-appearance: none;
        appearance: none;
    }
    /* The dropdown of secondary actions (Add / Browse / Sync / Settings). */
    .menu {
        position: absolute;
        top: calc(100% + 0.4rem);
        right: 0;
        z-index: 60;
        display: flex;
        flex-direction: column;
        min-width: 12rem;
        padding: 0.35rem;
        background: var(--canvas-elevated);
        border: 1px solid var(--border);
        border-radius: var(--sr-radius);
        box-shadow: var(--sr-shadow-lg);
    }
    .menu-item {
        text-align: left;
        border: 1px solid transparent;
        background: transparent;
        color: var(--fg);
        font-family: var(--sr-font-body);
        font-weight: 600;
        font-size: 0.85rem;
        padding: 0.6rem 0.8rem;
        border-radius: var(--sr-radius-sm);
        cursor: pointer;
        transition:
            background 0.15s ease,
            color 0.15s ease;
    }
    .menu-item:hover,
    .menu-item.on {
        color: var(--sr-accent);
        background: var(--sr-accent-weak);
    }
    .menu-item:focus-visible {
        outline: 2px solid var(--sr-focus);
        outline-offset: 2px;
    }

    /* Settings strip: a quiet row of app preferences under the top bar. On
       desktop the theme control + all three toggles sit on ONE line: each
       toggle's help text lives in a `title` tooltip (not inline), and the gaps
       are tight, so nothing wraps to a second row. On narrow widths flex-wrap
       lets them stack (the media query below allows the phone layout). */
    .settings-strip {
        position: relative;
        z-index: 40;
        flex: 0 0 auto;
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 0.55rem 1rem;
        padding: 0.75rem 1.25rem;
        background: var(--canvas-elevated);
        border-bottom: 1px solid var(--border);
        box-shadow: var(--sr-shadow-sm);
    }
    .setting {
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    .setting-label {
        font-family: var(--sr-font-body);
        font-weight: 700;
        font-size: 0.85rem;
        color: var(--fg);
        /* Keep each label on its own line so the row stays a single line. */
        white-space: nowrap;
    }
    /* Compact "AI is degraded to templated-only" marker; the full reason is in
       the setting's title tooltip (kept accessible there, not inline). */
    .warn-flag {
        color: var(--sr-tertiary);
        font-size: 0.9rem;
        line-height: 1;
        cursor: help;
    }

    /* Segmented control (theme). Transparent 1px border reserves space so the
       global button:hover border can't resize it. */
    .seg {
        display: inline-flex;
        border: 1px solid var(--border);
        border-radius: var(--sr-radius-pill);
        background: var(--sr-muted);
        padding: 0.2rem;
    }
    .seg-opt {
        border: 1px solid transparent;
        background: transparent;
        color: var(--fg-subtle);
        font-family: var(--sr-font-body);
        font-weight: 700;
        font-size: 0.78rem;
        padding: 0.3rem 0.9rem;
        border-radius: var(--sr-radius-pill);
        cursor: pointer;
        transition:
            background 0.2s ease,
            color 0.2s ease;
    }
    .seg-opt.on {
        color: var(--sr-accent);
        background: var(--canvas-elevated);
        box-shadow: var(--sr-shadow-sm);
    }
    .seg-opt:hover {
        color: var(--fg);
        border-color: transparent;
    }

    /* On/off switch */
    .switch {
        position: relative;
        width: 44px;
        height: 26px;
        flex: 0 0 auto;
        padding: 0;
        border: 1px solid var(--border);
        border-radius: 999px;
        background: var(--canvas-inset);
        cursor: pointer;
        transition:
            background 0.2s ease,
            border-color 0.2s ease;
    }
    .switch .knob {
        position: absolute;
        top: 2px;
        left: 2px;
        width: 20px;
        height: 20px;
        border-radius: 50%;
        background: var(--canvas-elevated);
        box-shadow: var(--sr-shadow-sm);
        transition: transform 0.18s ease;
    }
    .switch.on {
        background: var(--sr-accent);
        border-color: var(--sr-accent);
    }
    .switch.on .knob {
        transform: translateX(18px);
        background: var(--sr-on-accent);
    }
    .switch:focus-visible,
    .seg-opt:focus-visible {
        outline: 2px solid var(--sr-focus);
        outline-offset: 2px;
    }

    .content {
        position: relative;
        z-index: 1;
        flex: 1 1 auto;
        overflow-y: auto;
    }
    /* An opaque canvas under the embedded graphs so the shell's decorative
       bubble backdrop cannot bleed through the grid gaps or sparse-data areas.
       Matches the range box fill so the toolbar and surface read as one; the
       white graph cards float on it. min-height keeps the surface covering the
       viewport when there are few graphs. */
    .anki-graphs {
        min-height: 100%;
        background: var(--canvas);
    }
    /* Narrow widths: collapse the individual Add / Browse / Settings icons into
       the "☰" menu (they'd otherwise crowd the bar), keep the brand + menu on the
       first row, and drop the tab group onto its own second row (order: 3), so
       the top bar is at most two lines instead of three. */
    @media (max-width: 720px) {
        .desktop-action {
            display: none;
        }
        .mobile-menu-btn {
            display: inline-flex;
        }
        .topbar {
            padding-left: 1rem;
            padding-right: 1rem;
        }
        .tabs {
            order: 3;
            width: 100%;
            margin: 0;
            justify-content: center;
            /* All five tabs stay on one line; the tighter gap + tab padding
               below fit the short labels on a phone instead of wrapping Stats
               onto a second row. */
            flex-wrap: nowrap;
            gap: 0.3rem;
            height: auto;
        }
        .tab {
            padding: 0.5rem 0.55rem;
            font-size: 0.8rem;
            white-space: nowrap;
        }
    }

    /* Touch devices (the phone WebView): meet the ≥44px touch-target minimum
       from the design system. Scoped to coarse pointers so the desktop mouse
       layout (tighter top bar) is unchanged. */
    @media (pointer: coarse) {
        .tab,
        .menu-btn,
        .icon-btn {
            min-height: 44px;
            min-width: 44px;
        }
        /* Only .tab needs the flex centering here; the icon/menu buttons already
           get it from their base rule. Re-declaring display on .menu-btn would
           override the desktop `.mobile-menu-btn { display: none }` on a
           coarse-pointer wide screen and show the "☰" alongside the icons. */
        .tab {
            display: inline-flex;
            align-items: center;
            justify-content: center;
        }
        .menu-item {
            min-height: 44px;
        }
    }
</style>
