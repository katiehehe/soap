<!--
Copyright: Ankitects Pty Ltd and contributors
License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
-->
<script lang="ts">
    import { onMount } from "svelte";

    import { bridgeCommand, bridgeCommandsAvailable } from "@tslib/bridgecommand";

    import { subtopicTag, TAXONOMY } from "../study-map/lib";
    import { formulasForTag, type Formula } from "./formulas";
    import { mathjax } from "./mathjax";

    // An easy-to-reference Exam P formula sheet: every curated formula grouped by
    // the official syllabus (the same TAXONOMY the study map + scheduler use),
    // MathJax-rendered, and keyword-searchable. Each formula still records its
    // NAMED source in the data layer (formulas.ts) for traceability, but the
    // sheet no longer renders those citations. It is REFERENCE ONLY: it reads the
    // user's own added cards but never logs a review, schedules anything, or
    // changes any of the three scores. It sits alongside unlimited cram as the
    // other "just let me look things up" surface, so a candidate can check a
    // formula without it counting.

    // The user's own added flashcards, grouped by subtopic tag, fetched read-only
    // from the desktop bridge (speedrun-formula-cards). Empty in a plain browser
    // (tests / standalone preview), where the Anki bridge isn't present.
    interface UserCard {
        front: string;
        back: string;
    }
    let userCards: Record<string, UserCard[]> = {};
    // Bumped when the user's cards arrive so the MathJax action re-typesets them.
    let cardsVersion = 0;

    onMount(() => {
        if (!bridgeCommandsAvailable()) {
            return;
        }
        bridgeCommand("speedrun-formula-cards", (v) => {
            userCards = (v as Record<string, UserCard[]>) ?? {};
            cardsVersion += 1;
        });
    });

    // Keyword search + a unit filter. Both are pure view state, so they never
    // touch any score or the engine.
    let query = "";
    let unitFilter: "all" | string = "all";

    // Section identity only (DESIGN "Meaning-Only Accent Rule"): a calm accent per
    // unit for its heading marker + each card's TOP stripe. Never applied to the
    // formulas/numbers themselves.
    const UNIT_ACCENTS = [
        "var(--sr-accent)", // periwinkle for General Probability
        "var(--sr-secondary)", // sage for Univariate RVs
        "var(--sr-quinary)", // mauve for Multivariate RVs
    ];

    function matchesFormula(
        f: Formula,
        subName: string,
        unitName: string,
        q: string,
    ): boolean {
        if (!q) {
            return true;
        }
        return `${f.name} ${f.note ?? ""} ${f.latex} ${subName} ${unitName}`
            .toLowerCase()
            .includes(q);
    }

    function matchesCard(
        c: UserCard,
        subName: string,
        unitName: string,
        q: string,
    ): boolean {
        if (!q) {
            return true;
        }
        return `${c.front} ${c.back} ${subName} ${unitName}`.toLowerCase().includes(q);
    }

    interface SubView {
        id: string;
        name: string;
        tag: string;
        formulas: Formula[];
        cards: UserCard[];
    }
    interface UnitView {
        id: string;
        name: string;
        accent: string;
        subs: SubView[];
    }

    function buildUnits(
        q: string,
        filter: string,
        cards: Record<string, UserCard[]>,
    ): UnitView[] {
        return TAXONOMY.map((unit, i) => {
            const subs: SubView[] = unit.subtopics
                .map((sub) => {
                    const tag = subtopicTag(unit.id, sub.id);
                    return {
                        id: sub.id,
                        name: sub.name,
                        tag,
                        formulas: formulasForTag(tag).filter((f) =>
                            matchesFormula(f, sub.name, unit.name, q),
                        ),
                        cards: (cards[tag] ?? []).filter((c) =>
                            matchesCard(c, sub.name, unit.name, q),
                        ),
                    };
                })
                .filter((s) => s.formulas.length > 0 || s.cards.length > 0);
            return {
                id: unit.id,
                name: unit.name,
                accent: UNIT_ACCENTS[i % UNIT_ACCENTS.length],
                subs,
            };
        }).filter((u) => (filter === "all" || u.id === filter) && u.subs.length > 0);
    }

    // Rebuild the visible tree whenever the query, the unit filter, or the user's
    // cards change.
    $: q = query.trim().toLowerCase();
    $: visibleUnits = buildUnits(q, unitFilter, userCards);
    $: hasResults = visibleUnits.length > 0;
    // Re-typeset MathJax when the rendered set changes (cardsVersion covers the
    // async arrival of the user's own cards).
    $: mjDep = `${q}|${unitFilter}|${cardsVersion}|${visibleUnits.length}`;
</script>

<div class="formula-sheet">
    <div class="sheet">
        <header class="sheet-head">
            <p class="eyebrow">Reference</p>
            <h1>Formula sheet</h1>

            <div class="controls">
                <input
                    class="search"
                    type="text"
                    bind:value={query}
                    placeholder="Search formulas (e.g. variance, Poisson, Bayes)…"
                    aria-label="Search formulas"
                />
                <div class="unit-filters" role="group" aria-label="Filter by unit">
                    <button
                        class="filter"
                        class:on={unitFilter === "all"}
                        aria-pressed={unitFilter === "all"}
                        on:click={() => (unitFilter = "all")}
                    >
                        All units
                    </button>
                    {#each TAXONOMY as u}
                        <button
                            class="filter"
                            class:on={unitFilter === u.id}
                            aria-pressed={unitFilter === u.id}
                            on:click={() => (unitFilter = u.id)}
                        >
                            {u.name}
                        </button>
                    {/each}
                </div>
            </div>
        </header>

        {#if !hasResults}
            <p class="empty">
                No formulas match “{query}”. Try another keyword, or clear the search.
            </p>
        {/if}

        <div class="units" use:mathjax={mjDep}>
            {#each visibleUnits as unit (unit.id)}
                <section class="unit" style="--unit-accent:{unit.accent}">
                    <h2 class="unit-title">
                        <span class="unit-marker" aria-hidden="true"></span>
                        {unit.name}
                    </h2>

                    {#each unit.subs as sub (sub.tag)}
                        <section class="subtopic" style="--card-accent:{unit.accent}">
                            <h3 class="sub-title">{sub.name}</h3>

                            {#if sub.formulas.length > 0}
                                <ul class="formula-list">
                                    {#each sub.formulas as f (f.name)}
                                        <li class="formula">
                                            <div class="formula-body">
                                                <span class="formula-name">
                                                    {f.name}
                                                </span>
                                                <div class="formula-math">
                                                    {f.latex}
                                                </div>
                                                {#if f.note}
                                                    <p class="formula-note">
                                                        {f.note}
                                                    </p>
                                                {/if}
                                            </div>
                                        </li>
                                    {/each}
                                </ul>
                            {/if}

                            {#if sub.cards.length > 0}
                                <div class="user-cards">
                                    <p class="user-cards-head">Your added cards</p>
                                    {#each sub.cards as c, ci (ci)}
                                        <div class="user-card">
                                            <div class="uc-front">{c.front}</div>
                                            {#if c.back}
                                                <div class="uc-back">
                                                    {c.back}
                                                </div>
                                            {/if}
                                        </div>
                                    {/each}
                                </div>
                            {/if}
                        </section>
                    {/each}
                </section>
            {/each}
        </div>
    </div>
</div>

<style>
    .formula-sheet {
        /* Match the shared branded backdrop (the home shell's .app): a faint top
           accent wash over the canvas, with the static soap-ring layer painted by
           ::before. position + isolation give the rings a stacking context so
           they sit behind the content. */
        position: relative;
        isolation: isolate;
        min-height: 100%;
        background:
            radial-gradient(
                120% 80% at 50% -12%,
                var(--sr-accent-weak),
                transparent 60%
            ),
            var(--canvas);
        color: var(--fg);
        font-family: var(--sr-font-body);
    }
    /* Faint soap rings (thin circles, not filled dots) tinted to the theme
       accent, the same backdrop the home shell, study map, and readiness screens
       use, so the sheet reads as one product. Purely decorative: it sits behind
       the content, never intercepts clicks (pointer-events: none), and carries no
       motion, so the search box, filters, and formulas stay fully interactive and
       legible. The .formula-sheet root is already in the reduced-motion guardrail
       in base.scss, so this stays consistent for reduced-motion users too. */
    .formula-sheet::before {
        content: "";
        position: absolute;
        inset: 0;
        z-index: 0;
        pointer-events: none;
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
    }
    /* Lift the real content above the decorative ring layer. */
    .sheet {
        position: relative;
        z-index: 1;
        max-width: 900px;
        margin: 0 auto;
        padding: 2rem 1.5rem 4rem;
    }

    /* Header ---------------------------------------------------------------- */
    .eyebrow {
        margin: 0 0 0.3rem;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        color: var(--fg-subtle);
    }
    h1 {
        margin: 0;
        font-family: var(--sr-font-heading);
        font-weight: 600;
        font-size: clamp(2rem, 4.5vw, 2.8rem);
        line-height: 1.05;
        letter-spacing: -0.01em;
    }

    /* Controls -------------------------------------------------------------- */
    .controls {
        margin-top: 1.4rem;
        display: flex;
        flex-wrap: wrap;
        gap: 0.75rem;
        align-items: center;
    }
    .search {
        flex: 1 1 20rem;
        min-width: 0;
        padding: 0.65rem 0.85rem;
        font-family: var(--sr-font-body);
        font-size: 0.9rem;
        color: var(--fg);
        background: var(--canvas-inset);
        border: 1px solid var(--border);
        border-radius: var(--sr-radius-sm);
    }
    .search:focus-visible {
        outline: 2px solid var(--sr-focus);
        outline-offset: 2px;
    }
    .unit-filters {
        display: flex;
        flex-wrap: wrap;
        gap: 0.35rem;
    }
    .filter {
        border: 1px solid var(--border);
        background: var(--canvas-elevated);
        color: var(--fg-subtle);
        font-family: var(--sr-font-body);
        font-weight: 600;
        font-size: 0.78rem;
        padding: 0.5rem 0.85rem;
        border-radius: var(--sr-radius-pill);
        cursor: pointer;
        transition:
            border-color 0.2s ease,
            color 0.2s ease,
            background 0.2s ease;
    }
    .filter:hover {
        border-color: var(--sr-accent);
        color: var(--sr-accent);
        background: var(--sr-accent-weak);
    }
    .filter.on {
        border-color: var(--sr-accent);
        color: var(--sr-accent);
        background: var(--sr-accent-weak);
    }
    .filter:focus-visible {
        outline: 2px solid var(--sr-focus);
        outline-offset: 2px;
    }
    .empty {
        margin: 2rem 0;
        padding: 1.4rem;
        text-align: center;
        color: var(--fg-subtle);
        background: var(--canvas-elevated);
        border: 1px solid var(--border);
        border-radius: var(--sr-radius);
    }

    /* Units + subtopics ----------------------------------------------------- */
    .units {
        margin-top: 2rem;
        display: flex;
        flex-direction: column;
        gap: 2.25rem;
    }
    .unit {
        display: flex;
        flex-direction: column;
        gap: 1rem;
    }
    .unit-title {
        display: flex;
        align-items: center;
        gap: 0.6rem;
        margin: 0;
        font-family: var(--sr-font-heading);
        font-weight: 600;
        font-size: 1.5rem;
        letter-spacing: -0.01em;
    }
    .unit-marker {
        width: 0.85rem;
        height: 0.85rem;
        border-radius: 34%;
        background: var(--unit-accent);
        flex: 0 0 auto;
    }

    .subtopic {
        background: var(--sr-card-bg);
        border: 1px solid var(--border);
        border-radius: var(--sr-radius-lg);
        box-shadow:
            inset 0 3px 0 0 var(--card-accent),
            var(--sr-shadow-sm);
        padding: 1.3rem 1.4rem;
    }
    .sub-title {
        margin: 0 0 0.4rem;
        font-family: var(--sr-font-heading);
        font-weight: 600;
        font-size: 1.12rem;
    }

    .formula-list {
        list-style: none;
        margin: 0;
        padding: 0;
        display: flex;
        flex-direction: column;
    }
    .formula {
        display: flex;
        flex-wrap: wrap;
        align-items: baseline;
        justify-content: space-between;
        gap: 0.5rem 1rem;
        padding: 0.85rem 0;
        border-top: 1px solid var(--border-subtle);
    }
    .formula:first-child {
        border-top: none;
    }
    .formula-body {
        flex: 1 1 22rem;
        min-width: 0;
    }
    .formula-name {
        display: block;
        font-size: 0.74rem;
        font-weight: 700;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        color: var(--fg-subtle);
    }
    .formula-math {
        margin-top: 0.35rem;
        overflow-x: auto;
        overflow-y: hidden;
        /* Measured content stays high-contrast ink, never an accent colour. */
        color: var(--fg);
        font-size: 1.02rem;
    }
    /* MathJax renders \[ ... \] as a centred block; left-align it and drop the
       big default margins so the sheet reads as a compact list. */
    .formula-math :global(mjx-container[display="true"]) {
        margin: 0 !important;
        text-align: left !important;
    }
    .formula-note {
        margin: 0.35rem 0 0;
        font-size: 0.82rem;
        color: var(--fg-subtle);
        line-height: 1.5;
    }

    /* The user's own cards -------------------------------------------------- */
    .user-cards {
        margin-top: 1rem;
        padding-top: 0.9rem;
        border-top: 1px dashed var(--border);
    }
    .user-cards-head {
        margin: 0 0 0.6rem;
        font-size: 0.74rem;
        font-weight: 700;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        color: var(--fg-subtle);
    }
    .user-card {
        padding: 0.6rem 0.75rem;
        margin-bottom: 0.5rem;
        background: var(--canvas-inset);
        border: 1px solid var(--border-subtle);
        border-radius: var(--sr-radius-sm);
    }
    .user-card:last-child {
        margin-bottom: 0;
    }
    .uc-front {
        font-weight: 600;
        color: var(--fg);
    }
    .uc-back {
        margin-top: 0.25rem;
        color: var(--fg-subtle);
        line-height: 1.5;
    }

    @media (max-width: 620px) {
        .formula {
            flex-direction: column;
            /* Stretch (not baseline) so the stacked body spans the full card
               width; otherwise a wide equation sizes the body to its own width
               and pushes the whole page into horizontal scroll on a phone. */
            align-items: stretch;
        }
        .formula-body {
            /* Full card width so a too-wide formula scrolls inside
               .formula-math (overflow-x: auto), not the page. */
            flex: 1 1 auto;
            width: 100%;
        }
    }
</style>
