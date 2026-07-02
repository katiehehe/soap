<!--
Copyright: Ankitects Pty Ltd and contributors
License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
-->
<script lang="ts">
    import { bridgeCommand } from "@tslib/bridgecommand";

    // The concept map and readiness/stats screens are the existing SvelteKit
    // pages, reused here as the two tabs of the custom home shell (they still
    // work as standalone routes too).
    import ConceptMap from "../study-map/+page.svelte";
    import ReadinessStats from "../readiness-dashboard/+page.svelte";

    type Tab = "map" | "readiness";
    let tab: Tab = "map";

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
            <button
                class="tab"
                class:active={tab === "map"}
                on:click={() => (tab = "map")}
            >
                Concept map
            </button>
            <button
                class="tab"
                class:active={tab === "readiness"}
                on:click={() => (tab = "readiness")}
            >
                Readiness &amp; stats
            </button>
        </nav>

        <div class="actions">
            <button class="action primary" on:click={() => nav("study")}>
                Study now
            </button>
            <button class="action" on:click={() => nav("add")} title="Add a card">
                Add
            </button>
            <button class="action" on:click={() => nav("browse")} title="Browse cards">
                Browse
            </button>
            <button class="action" on:click={() => nav("sync")} title="Sync">
                Sync
            </button>
        </div>
    </header>

    <main class="content">
        {#if tab === "map"}
            <ConceptMap variant="map" />
        {:else}
            <ReadinessStats />
            <ConceptMap variant="panels" />
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
        /* --sr-accent / --sr-accent-weak come from the global theme tokens
           (ts/routes/base.scss) so the shell + concept map share one accent. */
        display: flex;
        flex-direction: column;
        height: 100vh;
        color: var(--fg, #1c1c1e);
        background: var(--canvas, #f6f7fb);
        font-family:
            "Inter",
            -apple-system,
            BlinkMacSystemFont,
            "Segoe UI",
            sans-serif;
    }

    /* Top bar — custom, so the app does not read as stock Anki. */
    .topbar {
        flex: 0 0 auto;
        display: flex;
        align-items: center;
        gap: 1rem;
        padding: 0.6rem 1rem;
        background: var(--canvas-elevated, #fff);
        border-bottom: 1px solid var(--border, #e6e7eb);
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
    }
    .brand {
        display: flex;
        align-items: center;
        gap: 0.55rem;
        flex: 0 0 auto;
    }
    .brand-mark {
        display: grid;
        place-items: center;
        width: 34px;
        height: 34px;
        border-radius: 9px;
        background: linear-gradient(135deg, var(--sr-accent), var(--sr-accent-2));
        color: #fff;
        font-weight: 800;
        font-size: 1.05rem;
    }
    .brand-text {
        display: flex;
        flex-direction: column;
        line-height: 1.05;
    }
    .brand-title {
        font-weight: 800;
        font-size: 0.98rem;
    }
    .brand-sub {
        font-size: 0.68rem;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: var(--fg-subtle, #8a8f98);
    }

    .tabs {
        display: flex;
        gap: 0.25rem;
        margin: 0 auto;
        background: var(--canvas-inset, #eef0f4);
        padding: 0.2rem;
        border-radius: 10px;
    }
    .tab {
        border: none;
        background: transparent;
        font: inherit;
        font-weight: 600;
        font-size: 0.9rem;
        color: var(--fg-subtle, #5b6069);
        padding: 0.4rem 0.9rem;
        border-radius: 8px;
        cursor: pointer;
        transition:
            background 0.12s ease,
            color 0.12s ease;
    }
    .tab:hover {
        color: var(--fg, #1c1c1e);
    }
    .tab.active {
        background: var(--canvas-elevated, #fff);
        color: var(--sr-accent);
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
    }

    .actions {
        display: flex;
        gap: 0.4rem;
        flex: 0 0 auto;
    }
    .action {
        border: 1px solid var(--border, #d7d9df);
        background: var(--canvas-elevated, #fff);
        color: var(--fg, #2a2d33);
        font: inherit;
        font-weight: 600;
        font-size: 0.85rem;
        padding: 0.4rem 0.8rem;
        border-radius: 8px;
        cursor: pointer;
        transition:
            filter 0.12s ease,
            background 0.12s ease;
    }
    .action:hover {
        background: var(--canvas-inset, #f0f1f5);
    }
    .action.primary {
        background: var(--sr-accent);
        border-color: var(--sr-accent);
        color: #fff;
    }
    .action.primary:hover {
        filter: brightness(1.06);
        background: var(--sr-accent);
    }

    .content {
        flex: 1 1 auto;
        overflow-y: auto;
    }

    @media (prefers-reduced-motion: reduce) {
        .tab,
        .action {
            transition: none;
        }
    }
</style>
