<!--
Copyright: Ankitects Pty Ltd and contributors
License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
-->
<script lang="ts">
    import type { CongratsInfoResponse } from "@generated/anki/scheduler_pb";
    import { congratsInfo } from "@generated/backend";
    import * as tr from "@generated/ftl";
    import { bridgeLink } from "@tslib/bridgecommand";

    import Col from "$lib/components/Col.svelte";
    import Container from "$lib/components/Container.svelte";

    import { buildNextLearnMsg } from "./lib";
    import { onMount } from "svelte";

    export let info: CongratsInfoResponse;
    export let refreshPeriodically = true;

    const congrats = tr.schedulingCongratulationsFinished();
    let nextLearnMsg: string;
    $: nextLearnMsg = buildNextLearnMsg(info);
    const today_reviews = tr.schedulingTodayReviewLimitReached();
    const today_new = tr.schedulingTodayNewLimitReached();

    const unburyThem = bridgeLink("unbury", tr.schedulingUnburyThem());
    const buriedMsg = tr.schedulingBuriedCardsFound({ unburyThem });
    const customStudy = bridgeLink("customStudy", tr.schedulingCustomStudy());
    const customStudyMsg = tr.schedulingHowToCustomStudy({
        customStudy,
    });

    onMount(() => {
        if (refreshPeriodically) {
            setInterval(async () => {
                try {
                    info = await congratsInfo({}, { alertOnError: false });
                } catch {
                    console.log("congrats fetch failed");
                }
            }, 60000);
        }
    });
</script>

<Container --gutter-block="1rem" --gutter-inline="2px" breakpoint="sm">
    <Col --col-justify="center">
        <div class="congrats">
            <div class="brand">
                <span class="brand-mark">P</span>
                <span class="brand-sub">Exam&nbsp;P · Speedrun</span>
            </div>

            <h1>{congrats}</h1>

            <p>{nextLearnMsg}</p>

            {#if info.reviewRemaining}
                <p>{today_reviews}</p>
            {/if}

            {#if info.newRemaining}
                <p>{today_new}</p>
            {/if}

            {#if info.bridgeCommandsSupported}
                {#if info.haveSchedBuried || info.haveUserBuried}
                    <p>
                        {@html buriedMsg}
                    </p>
                {/if}

                {#if !info.isFilteredDeck}
                    <p>
                        {@html customStudyMsg}
                    </p>
                {/if}
            {/if}

            {#if info.deckDescription}
                <div class="description">
                    {@html info.deckDescription}
                </div>
            {/if}
        </div>
    </Col>
</Container>

<style lang="scss">
    .congrats {
        margin: 2.5em auto 0;
        max-width: 30em;
        font-size: var(--font-size);
        font-family:
            "Inter",
            -apple-system,
            BlinkMacSystemFont,
            "Segoe UI",
            sans-serif;
        text-align: center;

        /* Card treatment so the post-review moment reads as the custom app. */
        background: var(--canvas-elevated, #fff);
        border: 1px solid var(--border-subtle, #e6e7eb);
        border-top: 4px solid var(--sr-accent, #6366f1);
        border-radius: var(--sr-radius, 12px);
        padding: 1.75rem 2rem 2rem;
        box-shadow: 0 6px 24px rgba(0, 0, 0, 0.06);

        :global(a) {
            color: var(--sr-accent, #6366f1);
            font-weight: 600;
            text-decoration: none;
        }
        :global(a:hover) {
            text-decoration: underline;
        }
    }

    .brand {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0.5rem;
        margin-bottom: 1rem;
    }
    .brand-mark {
        display: grid;
        place-items: center;
        width: 30px;
        height: 30px;
        border-radius: 8px;
        background: linear-gradient(
            135deg,
            var(--sr-accent, #6366f1),
            var(--sr-accent-2, #8b5cf6)
        );
        color: #fff;
        font-weight: 800;
    }
    .brand-sub {
        font-size: 0.7rem;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: var(--fg-subtle, #8a8f98);
    }

    h1 {
        font-size: 1.5rem;
        font-weight: 800;
        margin: 0 0 0.5rem;
    }

    .description {
        border: 1px solid var(--border);
        border-radius: var(--sr-radius, 10px);
        padding: 1em;
        margin-top: 1em;
        text-align: start;
    }
</style>
