<!--
Copyright: Ankitects Pty Ltd and contributors
License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
-->
<script lang="ts">
    import { onMount } from "svelte";
    import { slide } from "svelte/transition";

    import {
        bridgeCommand,
        bridgeCommandsAvailable,
    } from "@tslib/bridgecommand";

    // The concept map, progress panels, and readiness screens are the existing
    // SvelteKit pages, reused as the tabs of the custom home shell (they still
    // work as standalone routes too). Anki's own review-history graphs are
    // embedded INLINE in the Stats tab (below our coverage stats), so Anki never
    // feels like a separate app — no pop-out stats window.
    import Graphs from "../graphs/+page.svelte";
    import AddCard from "../add-card/+page.svelte";
    import ConceptMap from "../study-map/+page.svelte";
    import PracticeTest from "../practice-test/+page.svelte";
    import Readiness from "../readiness-dashboard/+page.svelte";
    import Metrics from "../metrics/+page.svelte";
    import FormulaSheet from "../formula-sheet/+page.svelte";
    import type { TestScope } from "../study-map/lib";
    import type { MetricId } from "../metrics/lib";

    // Task-focused tabs: the map, the daily plan, the Memory and Readiness
    // scores, formulas, coverage stats, and a "how it works" explainer.
    // Performance practice has no tab — it's launched from the map.
    type Tab =
        | "map"
        | "plan"
        | "memory"
        | "formula"
        | "readiness"
        | "stats"
        | "metrics";
    let tab: Tab = "map";
    // The "How it works" (metrics) tab can open anchored to one signal when the
    // user clicks a metric card on the readiness dashboard (the metricinfo event).
    let metricAnchor: MetricId | null = null;
    function onMetricInfo(e: CustomEvent<MetricId>): void {
        metricAnchor = e.detail;
        tab = "metrics";
        testActive = false;
    }
    // Practice-test mode is a focused overlay entered from a bubble's "Practice"
    // action — a subtopic, a unit, or the whole exam via the centre "Exam P"
    // bubble; it takes over the content area and returns to the map when done.
    // The map is the single entry point for practice (there is no Practice tab).
    let testActive = false;
    let testScope: TestScope = { kind: "all" };
    function onPracticeTest(e: CustomEvent<TestScope>): void {
        testScope = e.detail;
        testActive = true;
    }
    // Adding a card is a categorized overlay (front/back + a required subtopic),
    // not Anki's stock Add dialog — every card is filed under the syllabus.
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
    }
    let settings: Settings = {
        theme: "light",
        masteryScheduler: true,
        guided: false,
        aiEnabled: false,
        hasKey: false,
    };
    let settingsOpen = false;
    // Bumping this re-mounts the concept map so a scheduler change takes effect at
    // once (the map re-reads its tier-ordered inputs) without a full page reload.
    let mapKey = 0;

    // Guarded bridge call: the Anki webview provides window.bridgeCommand, but a
    // plain browser (tests, standalone preview) does not — so never throw there.
    function send(cmd: string, cb?: (v: unknown) => void): void {
        if (bridgeCommandsAvailable()) {
            bridgeCommand(cmd, cb);
        }
    }

    onMount(() => {
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

    // Each tab carries a muted scholarly accent used as its active colour.
    const TABS: { id: Tab; label: string; accent: string }[] = [
        { id: "map", label: "Map", accent: "var(--sr-accent)" },
        { id: "plan", label: "Plan", accent: "var(--sr-secondary)" },
        { id: "memory", label: "Memory", accent: "var(--sr-tertiary)" },
        { id: "formula", label: "Formulas", accent: "var(--sr-quinary)" },
        { id: "readiness", label: "Readiness", accent: "var(--sr-quinary)" },
        { id: "stats", label: "Stats", accent: "var(--sr-accent-2)" },
        { id: "metrics", label: "How it works", accent: "var(--sr-secondary)" },
    ];

    // Secondary toolbar actions.
    const ACTIONS: { where: string; label: string; title: string }[] = [
        { where: "add", label: "Add", title: "Add a card" },
        { where: "browse", label: "Browse", title: "Browse cards" },
        { where: "sync", label: "Sync", title: "Sync" },
    ];

    // Desktop actions are routed to the native Anki flows through the mw.web
    // bridge handler installed by the speedrunHome state (qt/aqt/speedrun.py).
    function nav(where: string): void {
        bridgeCommand("speedrun-nav:" + where);
    }
</script>

<div class="app">
    <header class="topbar">
        <div class="brand">
            <span class="brand-mark">P</span>
            <div class="brand-text">
                <span class="brand-title">Exam&nbsp;P</span>
                <span class="brand-sub">Speedrun</span>
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
                        metricAnchor = null;
                    }}
                >
                    {t.label}
                </button>
            {/each}
        </nav>

        <div class="actions">
            {#each ACTIONS as a}
                <button
                    class="chip"
                    title={a.title}
                    on:click={() =>
                        a.where === "add" ? (addActive = true) : nav(a.where)}
                >
                    {a.label}
                </button>
            {/each}
            <button
                class="chip settings-btn"
                class:active={settingsOpen}
                title="Settings"
                aria-expanded={settingsOpen}
                on:click={() => (settingsOpen = !settingsOpen)}
            >
                Settings
            </button>
        </div>
    </header>

    {#if settingsOpen}
        <div class="settings-strip" transition:slide={{ duration: 160 }}>
            <div class="setting">
                <div class="setting-text">
                    <span class="setting-label">Theme</span>
                    <span class="setting-desc">Light or dark academia</span>
                </div>
                <div class="seg" role="group" aria-label="Theme">
                    <button
                        class="seg-opt"
                        class:on={settings.theme === "light"}
                        on:click={() => setTheme(false)}>Light</button
                    >
                    <button
                        class="seg-opt"
                        class:on={settings.theme === "dark"}
                        on:click={() => setTheme(true)}>Dark</button
                    >
                </div>
            </div>

            <div class="setting">
                <div class="setting-text">
                    <span class="setting-label">Tiered mastery scheduling</span>
                    <span class="setting-desc">
                        Block → interleave, with a mastery gate. Off = plain review
                        order (the ablation).
                    </span>
                </div>
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

            <div class="setting">
                <div class="setting-text">
                    <span class="setting-label">Guided path</span>
                    <span class="setting-desc">
                        Walk the syllabus in order; holds a topic until its
                        prerequisites are practiced. Off = free choice.
                    </span>
                </div>
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

            <div class="setting">
                <div class="setting-text">
                    <span class="setting-label">AI practice</span>
                    <span class="setting-desc">
                        Adds model-written, self-verified problems.
                        {#if settings.aiEnabled && !settings.hasKey}
                            <span class="warn">no API key — templated only</span>
                        {/if}
                    </span>
                </div>
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
                <ConceptMap variant="map" on:practicetest={onPracticeTest} />
            {/key}
        {:else if tab === "plan"}
            {#key mapKey}
                <ConceptMap variant="plan" on:practicetest={onPracticeTest} />
            {/key}
        {:else if tab === "memory"}
            {#key mapKey}
                <ConceptMap variant="memory" on:practicetest={onPracticeTest} />
            {/key}
        {:else if tab === "formula"}
            <FormulaSheet />
        {:else if tab === "stats"}
            {#key mapKey}
                <ConceptMap variant="stats" on:practicetest={onPracticeTest} />
            {/key}
            <div class="anki-graphs">
                <h2 class="graphs-title">Review history (Anki stats)</h2>
                <Graphs />
            </div>
        {:else if tab === "metrics"}
            <Metrics anchor={metricAnchor} />
        {:else}
            <Readiness embedded on:metricinfo={onMetricInfo} />
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
    /* Faint graph-paper dot grid — scholarly texture, easy on the eyes. */
    .app::before {
        content: "";
        position: absolute;
        inset: 0;
        background-image: radial-gradient(
            circle,
            rgba(129, 137, 214, 0.05) 1px,
            transparent 1.2px
        );
        background-size: 26px 26px;
        pointer-events: none;
        z-index: 0;
    }

    /* Top bar — solid and quiet, one hairline underline. */
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
        border-radius: 11px;
        background: linear-gradient(135deg, var(--sr-accent), var(--sr-accent-2));
        color: #fbfaf6;
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
        font-size: 1.2rem;
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
           visually without ever resizing the row — the bar can't shift. */
        box-sizing: border-box;
        height: 2.85rem;
    }
    .tab {
        /* Reserve a transparent border so the global button:hover (which adds a
           1px border) can't resize the tab and shift its neighbours. */
        border: 1px solid transparent;
        background: transparent;
        font-family: var(--sr-font-body);
        font-weight: 700;
        font-size: 0.82rem;
        color: var(--fg-subtle);
        padding: 0.5rem 1.15rem;
        border-radius: var(--sr-radius-pill);
        cursor: pointer;
        transform-origin: center;
        /* Hover only scales the button — a transform changes its painted size, not
           the bar's layout, so the top bar never shifts up/down. */
        transition:
            transform 0.15s ease,
            background 0.2s ease,
            color 0.2s ease;
    }
    .tab:hover {
        color: var(--fg);
        border-color: transparent;
        transform: scale(1.05);
    }
    .tab:active {
        transform: scale(0.97);
    }
    .tab.active {
        color: var(--tab-accent);
        /* With no container behind the group, the active view reads as its own
           accent-tinted pill (soft fill + faint ring) on the bare top bar. The
           ring reuses the reserved transparent border, so nothing shifts. */
        background: color-mix(in srgb, var(--tab-accent) 14%, transparent);
        border-color: color-mix(in srgb, var(--tab-accent) 32%, transparent);
    }
    .tab:focus-visible {
        outline: 2px solid var(--sr-focus);
        outline-offset: 2px;
    }

    .actions {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 0.45rem;
        /* Equal-width flank, right-aligned, so the tabs stay centered. */
        flex: 1 1 0;
        min-width: 0;
        justify-content: flex-end;
    }
    .chip {
        border: 1px solid var(--border);
        background: var(--canvas-elevated);
        color: var(--fg);
        font-family: var(--sr-font-body);
        font-weight: 600;
        font-size: 0.8rem;
        padding: 0 0.95rem;
        min-height: 40px;
        border-radius: var(--sr-radius-sm);
        cursor: pointer;
        transition:
            border-color 0.2s ease,
            color 0.2s ease,
            background 0.2s ease;
    }
    .chip:hover {
        border-color: var(--sr-accent);
        color: var(--sr-accent);
        background: var(--sr-accent-weak);
    }
    .chip:focus-visible {
        outline: 2px solid var(--sr-focus);
        outline-offset: 2px;
    }
    .settings-btn.active {
        border-color: var(--sr-accent);
        color: var(--sr-accent);
        background: var(--sr-accent-weak);
    }

    /* Settings strip — a quiet row of app preferences under the top bar. */
    .settings-strip {
        position: relative;
        z-index: 40;
        flex: 0 0 auto;
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 0.9rem 2.25rem;
        padding: 1rem 1.5rem;
        background: var(--canvas-elevated);
        border-bottom: 1px solid var(--border);
        box-shadow: var(--sr-shadow-sm);
    }
    .setting {
        display: flex;
        align-items: center;
        gap: 0.9rem;
    }
    .setting-text {
        display: flex;
        flex-direction: column;
        gap: 0.12rem;
        max-width: 20rem;
    }
    .setting-label {
        font-family: var(--sr-font-body);
        font-weight: 700;
        font-size: 0.85rem;
        color: var(--fg);
    }
    .setting-desc {
        font-size: 0.72rem;
        color: var(--fg-subtle);
        line-height: 1.3;
    }
    .warn {
        color: var(--sr-tertiary);
        font-weight: 600;
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
        background: #fbfaf6;
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
    /* Anki's review graphs, embedded inline under the coverage stats. */
    .anki-graphs {
        margin-top: 1.75rem;
        padding-top: 1.5rem;
        border-top: 1px solid var(--border);
    }
    .graphs-title {
        font-family: var(--sr-font-heading);
        font-weight: 800;
        font-size: 1.2rem;
        margin: 0 1.25rem 0.75rem;
        color: var(--fg);
    }

    /* Narrow widths: stack the toolbar (brand / tabs / actions each on their own
       row) so the action buttons wrap in-viewport instead of overflowing. */
    @media (max-width: 720px) {
        .tabs {
            width: 100%;
            margin: 0;
            justify-content: center;
            /* All tabs must stay reachable on a phone: let the group wrap to as
               many rows as it needs (auto height) instead of overflowing its
               width and clipping "Map"/"Plan" or spilling the last tabs. */
            flex-wrap: wrap;
            height: auto;
            row-gap: 0.3rem;
        }
        .actions {
            width: 100%;
            justify-content: center;
        }
    }
</style>
