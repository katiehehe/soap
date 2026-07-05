<!--
Copyright: Ankitects Pty Ltd and contributors
License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
-->
<!--
  SOAP brand mark — a little bar of soap with rising bubbles. Drawn in
  currentColor so it inherits the colour of whatever it sits on (e.g. the
  --sr-on-accent foam colour inside the brand tile). Decorative only.
-->
<script lang="ts">
    export let size: number | string = 28;
    export let title = "SOAP";
</script>

<svg
    class="brandmark"
    width={size}
    height={size}
    viewBox="0 0 24 24"
    role="img"
    aria-label={title}
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
>
    <!-- the soap bar -->
    <rect x="3" y="13" width="18" height="8" rx="3.1" fill="currentColor" />
    <!-- gloss streak across the bar -->
    <rect
        x="5.2"
        y="14.9"
        width="7"
        height="1.6"
        rx="0.8"
        fill="currentColor"
        opacity="0.4"
    />
    <!-- bubbles rising off the bar -->
    <circle cx="8" cy="7.2" r="3" fill="none" stroke="currentColor" stroke-width="1.5" />
    <circle cx="14.6" cy="6" r="2" fill="currentColor" />
    <circle cx="12" cy="10.2" r="1.3" fill="currentColor" />
</svg>

<style>
    .brandmark {
        display: block;
    }
</style>
