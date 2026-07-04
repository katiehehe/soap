<!--
Copyright: Ankitects Pty Ltd and contributors
License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
-->
<script lang="ts">
    import { onMount } from "svelte";

    import {
        bridgeCommand,
        bridgeCommandsAvailable,
    } from "@tslib/bridgecommand";

    import { subtopicTag, TAXONOMY } from "../study-map/lib";
    import { FORMULAS, formulasForTag, type Formula } from "./formulas";
    import { mathjax } from "./mathjax";

    // An easy-to-reference Exam P formula sheet: every curated formula grouped by
    // the official syllabus (the same TAXONOMY the study map + scheduler use),
    // MathJax-rendered, keyword-searchable, and each one traceable to a NAMED
    // source. It is REFERENCE ONLY — it reads the user's own added cards but
    // never logs a review, schedules anything, or changes any of the three
    // scores. It sits alongside unlimited cram as the other "just let me look
    // things up" surface, so a candidate can check a formula without it counting.

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

    // Keyword search + a unit filter. Both are pure view state — they never touch
    // any score or the engine.
    let query = "";
    let unitFilter: "all" | string = "all";

    // Section identity only (DESIGN "Meaning-Only Accent Rule"): a calm accent per
    // unit for its heading marker + each card's TOP stripe. Never applied to the
    // formulas/numbers themselves.
    const UNIT_ACCENTS = [
        "var(--sr-accent)", // periwinkle — General Probability
        "var(--sr-secondary)", // sage — Univariate RVs
        "var(--sr-quinary)", // mauve — Multivariate RVs
    ];

    const TOTAL_FORMULAS = Object.values(FORMULAS).reduce(
        (sum, list) => sum + list.length,
        0,
    );
    const TOTAL_SUBTOPICS = TAXONOMY.reduce(
        (sum, u) => sum + u.subtopics.length,
        0,
    );

    function matchesFormula(
        f: Formula,
        subName: string,
        unitName: string,
        q: string,
    ): boolean {
        if (!q) {
            return true;
        }
        return `${f.name} ${f.note ?? ""} ${f.source} ${f.latex} ${subName} ${unitName}`
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
        return `${c.front} ${c.back} ${subName} ${unitName}`
            .toLowerCase()
            .includes(q);
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
        }).filter(
            (u) => (filter === "all" || u.id === filter) && u.subs.length > 0,
        );
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
            <p class="lede">
                Every Exam&nbsp;P formula, grouped by the official syllabus. Look
                anything up as you study — {TOTAL_FORMULAS} formulas across the
                {TOTAL_SUBTOPICS} subtopics, each traceable to a named source.
            </p>
            <p class="ref-only" role="note">
                Reference only — this page never logs a review, schedules a card,
                or changes your Memory, Performance, or Readiness scores.
            </p>

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

            <p class="sources">
                Sources: SOA&nbsp;Exam&nbsp;P syllabus · Ross, <i
                    >A First Course in Probability</i
                >
                · Hassett&nbsp;&amp;&nbsp;Stewart,
                <i>Probability for Risk Management</i>.
            </p>
        </header>

        {#if !hasResults}
            <p class="empty">
                No formulas match “{query}”. Try another keyword, or clear the
                search.
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
                        <section
                            class="subtopic"
                            style="--card-accent:{unit.accent}"
                        >
                            <h3 class="sub-title">{sub.name}</h3>

                            {#if sub.formulas.length > 0}
                                <ul class="formula-list">
                                    {#each sub.formulas as f (f.name)}
                                        <li class="formula">
                                            <div class="formula-body">
                                                <span class="formula-name"
                                                    >{f.name}</span
                                                >
                                                <div class="formula-math">
                                                    {f.latex}
                                                </div>
                                                {#if f.note}
                                                    <p class="formula-note">
                                                        {f.note}
                                                    </p>
                                                {/if}
                                            </div>
                                            <span class="formula-source"
                                                >{f.source}</span
                                            >
                                        </li>
                                    {/each}
                                </ul>
                            {/if}

                            {#if sub.cards.length > 0}
                                <div class="user-cards">
                                    <p class="user-cards-head">
                                        Your added cards
                                        <span class="user-cards-sub"
                                            >your own notes · not scored</span
                                        >
                                    </p>
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
        min-height: 100%;
        background: var(--canvas);
        color: var(--fg);
        font-family: var(--sr-font-body);
    }
    .sheet {
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
    .lede {
        margin: 0.6rem 0 0;
        max-width: 62ch;
        color: var(--fg-subtle);
        line-height: 1.55;
    }
    .ref-only {
        margin: 0.9rem 0 0;
        display: inline-block;
        padding: 0.45rem 0.8rem;
        font-size: 0.78rem;
        color: var(--fg-subtle);
        background: var(--canvas-inset);
        border: 1px solid var(--border);
        border-radius: var(--sr-radius-sm);
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
    .sources {
        margin: 1rem 0 0;
        font-size: 0.78rem;
        color: var(--fg-subtle);
        line-height: 1.5;
    }
    .sources i {
        font-style: italic;
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
        border-top: var(--sr-border-heavy) solid var(--card-accent);
        border-radius: var(--sr-radius-lg);
        box-shadow: var(--sr-shadow-sm);
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
        /* Measured content stays high-contrast ink — never an accent colour. */
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
    .formula-source {
        flex: 0 0 auto;
        align-self: flex-start;
        margin-top: 0.35rem;
        font-size: 0.72rem;
        color: var(--fg-subtle);
        white-space: nowrap;
    }

    /* The user's own cards -------------------------------------------------- */
    .user-cards {
        margin-top: 1rem;
        padding-top: 0.9rem;
        border-top: 1px dashed var(--border);
    }
    .user-cards-head {
        margin: 0 0 0.6rem;
        display: flex;
        flex-wrap: wrap;
        align-items: baseline;
        gap: 0.5rem;
        font-size: 0.74rem;
        font-weight: 700;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        color: var(--fg-subtle);
    }
    .user-cards-sub {
        font-size: 0.68rem;
        font-weight: 600;
        letter-spacing: 0;
        text-transform: none;
        color: var(--fg-subtle);
        opacity: 0.85;
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
        }
        .formula-source {
            margin-top: 0;
        }
    }
</style>
