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
        max-width: 32em;
        font-size: var(--font-size);
        font-family: var(--sr-font-body, sans-serif);
        color: var(--fg);
        text-align: center;

        /* A warm, quiet "you finished" card — a green top accent marks the win. */
        background-color: var(--canvas-elevated);
        border: 1px solid var(--border);
        border-top: 3px solid var(--sr-mastered);
        border-radius: var(--sr-radius);
        padding: 2.25rem 2rem 2.5rem;
        box-shadow: var(--sr-shadow);

        :global(a) {
            color: var(--sr-accent);
            font-weight: 700;
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
        gap: 0.55rem;
        margin-bottom: 1.25rem;
    }
    .brand-mark {
        display: grid;
        place-items: center;
        width: 36px;
        height: 36px;
        border-radius: 10px;
        background: linear-gradient(135deg, var(--sr-accent), var(--sr-accent-2));
        color: #fbfaf6;
        font-family: var(--sr-font-heading, serif);
        font-weight: 700;
        font-size: 1rem;
        box-shadow: var(--sr-shadow-sm);
    }
    .brand-sub {
        font-family: var(--sr-font-body, sans-serif);
        font-size: 0.64rem;
        font-weight: 700;
        letter-spacing: 0.2em;
        text-transform: uppercase;
        color: var(--fg-subtle);
    }

    h1 {
        font-family: var(--sr-font-heading, serif);
        font-size: clamp(1.7rem, 4.5vw, 2.4rem);
        font-weight: 600;
        line-height: 1.1;
        letter-spacing: -0.01em;
        margin: 0 0 0.75rem;
        color: var(--fg);
    }

    .description {
        border: 1px solid var(--border);
        border-radius: var(--sr-radius-sm);
        padding: 1em;
        margin-top: 1.25em;
        text-align: start;
    }
</style>
