<!--
Copyright: Ankitects Pty Ltd and contributors
License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
-->
<script lang="ts">
    import "./base.scss";

    // Self-hosted fonts for the Speedrun UI (Fontsource → bundled by Vite, so
    // they work offline in the desktop webview). Academic pairing: Fraunces (a
    // scholarly old-style serif) for headings against DM Sans for body/UI. Only
    // *referenced* by the speedrun screens via --sr-font-* tokens; stock Anki
    // screens keep their own font stack.
    import "@fontsource-variable/fraunces/index.css";
    import "@fontsource-variable/dm-sans/index.css";

    import { setContext } from "svelte";

    import { modalsKey, touchDeviceKey } from "$lib/components/context-keys";

    setContext(modalsKey, new Map());
    setContext(touchDeviceKey, "ontouchstart" in document.documentElement);
</script>

<slot />
