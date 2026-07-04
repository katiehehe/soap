<!--
Copyright: Ankitects Pty Ltd and contributors
License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
-->
<!--
  Maximalist button. Four variants (primary / secondary / outline / ghost) and
  three sizes. `accent` (a CSS colour, e.g. accentVarAt(i)) drives the
  secondary/outline/ghost variants; primary uses the fixed 3-accent gradient.

  Legibility: the primary label carries a dark text-halo so white stays readable
  even over the light (cyan) end of the gradient. secondary/outline/ghost keep
  text on --fg or the accent for guaranteed contrast.
-->
<script lang="ts">
    export let variant: "primary" | "secondary" | "outline" | "ghost" = "primary";
    export let size: "sm" | "md" | "lg" = "md";
    export let accent = "var(--sr-accent)";
    export let type: "button" | "submit" | "reset" = "button";
    export let href: string | null = null;
    export let disabled = false;
    export let title: string | null = null;
    export let ariaLabel: string | null = null;

    let klass = "";
    export { klass as class };
</script>

{#if href}
    <a
        class="sr-btn {variant} {size} {klass}"
        style="--btn-accent:{accent}"
        {href}
        {title}
        aria-label={ariaLabel}
        on:click
    >
        <slot />
    </a>
{:else}
    <button
        class="sr-btn {variant} {size} {klass}"
        style="--btn-accent:{accent}"
        {type}
        {disabled}
        {title}
        aria-label={ariaLabel}
        on:click
    >
        <slot />
    </button>
{/if}

<style>
    .sr-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 0.5rem;
        border-radius: var(--sr-radius-pill);
        font-family: var(--sr-font-body);
        font-weight: 700;
        letter-spacing: 0;
        text-decoration: none;
        cursor: pointer;
        white-space: nowrap;
        border: 1px solid transparent;
        transition:
            box-shadow 0.2s ease,
            background-color 0.2s ease,
            color 0.2s ease;
    }

    /* Sizes — all ≥ 44px tall (touch target). */
    .sm {
        height: 42px;
        padding: 0 1.15rem;
        font-size: 0.78rem;
    }
    .md {
        height: 56px;
        padding: 0 2.4rem;
        font-size: 0.95rem;
    }
    .lg {
        height: 64px;
        padding: 0 3rem;
        font-size: 1.05rem;
    }

    /* Primary — solid indigo, ivory text, gentle elevation. */
    .primary {
        color: #fbfaf6;
        border-color: transparent;
        background: var(--sr-accent);
        box-shadow: var(--sr-shadow-sm);
    }
    .primary:hover:not(:disabled) {
        background: var(--sr-accent-2);
        box-shadow: var(--sr-shadow);
    }

    /* Secondary — quiet accent outline that tints on hover. */
    .secondary {
        color: var(--btn-accent);
        background: transparent;
        border-color: var(--btn-accent);
    }
    .secondary:hover:not(:disabled) {
        background: var(--sr-accent-weak);
    }

    /* Outline — bordered, soft elevation; text stays on --fg (always readable). */
    .outline {
        color: var(--fg);
        background: var(--canvas-elevated);
        border-color: var(--btn-accent);
        box-shadow: var(--sr-shadow-sm);
    }
    .outline:hover:not(:disabled) {
        background: var(--sr-accent-weak);
    }

    /* Ghost — plain text with a quiet underline. */
    .ghost {
        color: var(--sr-accent);
        background: transparent;
        border-color: transparent;
        text-decoration: underline;
        text-underline-offset: 4px;
        border-radius: var(--sr-radius-sm);
    }
    .ghost:hover:not(:disabled) {
        background: var(--sr-accent-weak);
    }

    .sr-btn:active:not(:disabled) {
        transform: scale(0.98);
    }

    /* Focus — visible ring with offset. */
    .sr-btn:focus-visible {
        outline: 2px solid var(--sr-focus);
        outline-offset: 2px;
    }

    .sr-btn:disabled {
        opacity: 0.5;
        cursor: not-allowed;
        filter: saturate(0.6);
    }
</style>
