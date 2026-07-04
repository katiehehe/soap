<!--
Copyright: Ankitects Pty Ltd and contributors
License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
-->
<script lang="ts">
    import { createEventDispatcher } from "svelte";

    import { bridgeCommand } from "@tslib/bridgecommand";

    import { subtopicTag, TAXONOMY } from "../study-map/lib";

    // Add a flashcard to the single-exam deck. Every card must be CATEGORIZED into
    // one of the 19 syllabus subtopics — picked manually or suggested by the
    // classifier — so it files into the right SOA Exam P subdeck and counts toward
    // coverage/mastery. There are no loose/uncategorized cards and no ad-hoc decks.

    interface Suggestion {
        tag: string;
        name: string;
        source: string;
    }
    interface ClassifyResult {
        provider: string;
        suggestions: Suggestion[];
    }
    interface AddResult {
        ok: boolean;
        deck?: string;
        error?: string;
    }

    const dispatch = createEventDispatcher<{ done: void }>();

    let front = "";
    let back = "";
    let subtopic = "";
    let suggestions: Suggestion[] = [];
    let provider = "";
    let suggesting = false;
    let saving = false;
    let error = "";
    let savedMsg = "";

    $: canSave = front.trim() !== "" && back.trim() !== "" && subtopic !== "";
    const NAME_BY_TAG = new Map(
        TAXONOMY.flatMap((u) =>
            u.subtopics.map((s) => [subtopicTag(u.id, s.id), s.name] as const),
        ),
    );

    function suggest(): void {
        if (front.trim() === "") {
            error = "Type the front first, then suggest a topic.";
            return;
        }
        error = "";
        suggesting = true;
        bridgeCommand(`speedrun-classify:${front}`, (r: ClassifyResult) => {
            suggesting = false;
            suggestions = r?.suggestions ?? [];
            provider = r?.provider ?? "";
            // Pre-select the top suggestion if the user hasn't chosen one.
            if (!subtopic && suggestions.length) {
                subtopic = suggestions[0].tag;
            }
        });
    }

    function save(): void {
        if (!canSave || saving) {
            return;
        }
        saving = true;
        error = "";
        savedMsg = "";
        const payload = JSON.stringify({ front, back, subtopic });
        bridgeCommand(`speedrun-add-card:${payload}`, (r: AddResult) => {
            saving = false;
            if (r?.ok) {
                savedMsg = `Added to ${NAME_BY_TAG.get(subtopic) ?? "the deck"}.`;
                // Keep the subtopic selected for a quick next card; clear the text.
                front = "";
                back = "";
                suggestions = [];
            } else {
                error = r?.error ?? "Couldn't add the card.";
            }
        });
    }
</script>

<div class="add">
    <section class="card">
        <h1>Add a card</h1>
        <p class="lead">
            Cards live in the <b>SOA Exam P</b>
            deck only, so every card is filed under a syllabus subtopic. Pick one, or
            let the classifier suggest it from your question.
        </p>

        <label class="field">
            <span class="flabel">Front (question)</span>
            <textarea
                bind:value={front}
                rows="3"
                placeholder="e.g. State the variance of a Poisson(λ)."
            ></textarea>
        </label>

        <label class="field">
            <span class="flabel">Back (answer)</span>
            <textarea
                bind:value={back}
                rows="3"
                placeholder="e.g. Var(X) = λ."
            ></textarea>
        </label>

        <div class="field">
            <div class="flabel-row">
                <span class="flabel">Subtopic</span>
                <button class="suggest" on:click={suggest} disabled={suggesting}>
                    {suggesting ? "Suggesting…" : "Suggest topic"}
                </button>
            </div>
            <select bind:value={subtopic} class="subtopic">
                <option value="" disabled>Choose a subtopic…</option>
                {#each TAXONOMY as u}
                    <optgroup label={u.name}>
                        {#each u.subtopics as s}
                            <option value={subtopicTag(u.id, s.id)}>{s.name}</option>
                        {/each}
                    </optgroup>
                {/each}
            </select>

            {#if suggestions.length}
                <div class="suggestions">
                    <span class="sug-label">
                        {provider === "openai" ? "AI suggestions" : "Keyword suggestions"}
                    </span>
                    {#each suggestions as sug}
                        <button
                            class="sug-chip"
                            class:active={subtopic === sug.tag}
                            title="Matched against: {sug.source}"
                            on:click={() => (subtopic = sug.tag)}
                        >
                            {sug.name}
                        </button>
                    {/each}
                </div>
            {/if}
        </div>

        {#if error}
            <p class="msg error">{error}</p>
        {:else if savedMsg}
            <p class="msg ok">{savedMsg} Add another, or go back.</p>
        {/if}

        <div class="actions">
            <button class="btn primary" on:click={save} disabled={!canSave || saving}>
                {saving ? "Adding…" : "Add card"}
            </button>
            <button class="btn ghost" on:click={() => dispatch("done")}>Done</button>
        </div>
    </section>
</div>

<style>
    .add {
        max-width: 680px;
        margin: 0 auto;
        padding: 2rem 1.5rem 3rem;
        font-family: var(--sr-font-body);
        color: var(--fg);
    }
    .card {
        background: var(--canvas-elevated);
        border: 1px solid var(--border);
        border-radius: var(--sr-radius, 16px);
        box-shadow: var(--sr-shadow-sm);
        padding: 1.75rem;
    }
    h1 {
        font-family: var(--sr-font-heading);
        font-weight: 800;
        font-size: 1.5rem;
        letter-spacing: -0.01em;
        margin: 0 0 0.4rem;
    }
    .lead {
        font-size: 0.95rem;
        line-height: 1.55;
        color: var(--fg-subtle);
        margin: 0 0 1.3rem;
    }
    .field {
        display: block;
        margin-bottom: 1.1rem;
    }
    .flabel {
        display: block;
        font-size: 0.72rem;
        font-weight: 800;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: var(--fg-subtle);
        margin-bottom: 0.4rem;
    }
    .flabel-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        margin-bottom: 0.4rem;
    }
    .flabel-row .flabel {
        margin-bottom: 0;
    }
    textarea,
    .subtopic {
        width: 100%;
        box-sizing: border-box;
        font-family: var(--sr-font-body);
        font-size: 0.95rem;
        color: var(--fg);
        background: var(--canvas);
        border: 1px solid var(--border);
        border-radius: var(--sr-radius-sm, 10px);
        padding: 0.6rem 0.75rem;
        resize: vertical;
    }
    textarea:focus,
    .subtopic:focus {
        outline: none;
        border-color: var(--sr-accent);
        box-shadow: 0 0 0 3px var(--sr-accent-weak);
    }
    .suggest {
        border: 1px solid var(--sr-accent);
        background: var(--sr-accent-weak);
        color: var(--sr-accent);
        font-family: var(--sr-font-body);
        font-weight: 700;
        font-size: 0.78rem;
        padding: 0.3rem 0.75rem;
        border-radius: var(--sr-radius-pill, 999px);
        cursor: pointer;
    }
    .suggest:disabled {
        opacity: 0.6;
        cursor: default;
    }
    .suggestions {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 0.4rem;
        margin-top: 0.6rem;
    }
    .sug-label {
        font-size: 0.68rem;
        font-weight: 700;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: var(--fg-subtle);
        margin-right: 0.2rem;
    }
    .sug-chip {
        border: 1px solid var(--border);
        background: var(--canvas);
        color: var(--fg);
        font-family: var(--sr-font-body);
        font-weight: 600;
        font-size: 0.82rem;
        padding: 0.3rem 0.7rem;
        border-radius: var(--sr-radius-pill, 999px);
        cursor: pointer;
    }
    .sug-chip:hover {
        border-color: var(--sr-accent);
    }
    .sug-chip.active {
        border-color: var(--sr-accent);
        background: var(--sr-accent);
        color: #fbfaf6;
    }
    .msg {
        font-size: 0.9rem;
        border-radius: 10px;
        padding: 0.6rem 0.8rem;
        margin: 0 0 1rem;
    }
    .msg.error {
        color: #c0392b;
        background: color-mix(in srgb, #c0392b 10%, transparent);
        border: 1px solid color-mix(in srgb, #c0392b 40%, var(--border));
    }
    .msg.ok {
        color: #2f855a;
        background: color-mix(in srgb, #2f855a 10%, transparent);
        border: 1px solid color-mix(in srgb, #2f855a 40%, var(--border));
    }
    .actions {
        display: flex;
        gap: 0.6rem;
        flex-wrap: wrap;
    }
    .btn {
        font-family: var(--sr-font-body);
        font-weight: 700;
        font-size: 0.95rem;
        padding: 0.65rem 1.3rem;
        border-radius: var(--sr-radius-sm, 10px);
        border: 1px solid transparent;
        cursor: pointer;
    }
    .btn.primary {
        background: var(--sr-accent);
        color: #fbfaf6;
        box-shadow: var(--sr-shadow-sm);
    }
    .btn.primary:disabled {
        background: var(--canvas-inset);
        color: var(--fg-subtle);
        box-shadow: none;
        cursor: not-allowed;
    }
    .btn.ghost {
        background: transparent;
        border-color: var(--border);
        color: var(--fg);
    }
    .btn.ghost:hover {
        border-color: var(--sr-accent);
        color: var(--sr-accent);
    }
</style>
