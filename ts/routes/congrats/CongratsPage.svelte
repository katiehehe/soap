<!--
Copyright: Ankitects Pty Ltd and contributors
License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
-->
<script lang="ts">
    import type { CongratsInfoResponse } from "@generated/anki/scheduler_pb";
    import { congratsInfo } from "@generated/backend";
    import * as tr from "@generated/ftl";
    import { bridgeCommand, bridgeLink } from "@tslib/bridgecommand";

    import Col from "$lib/components/Col.svelte";
    import Container from "$lib/components/Container.svelte";
    import BrandMark from "../speedrun-ui/BrandMark.svelte";

    import { buildNextLearnMsg } from "./lib";
    import { onMount } from "svelte";

    export let info: CongratsInfoResponse;
    export let refreshPeriodically = true;

    // Decorative rising soap bubbles for the celebration (honours reduced-motion
    // via the global guardrail in base.scss). Purely cosmetic.
    const bubbleSeeds = [
        { left: 8, size: 14, delay: 0, dur: 7 },
        { left: 22, size: 9, delay: 1.4, dur: 6 },
        { left: 39, size: 18, delay: 0.6, dur: 8.2 },
        { left: 55, size: 11, delay: 2.1, dur: 6.6 },
        { left: 69, size: 8, delay: 1.0, dur: 5.6 },
        { left: 84, size: 15, delay: 0.35, dur: 7.6 },
        { left: 93, size: 10, delay: 2.6, dur: 6.1 },
    ];

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

    // Speedrun navigation off the end-of-deck screen: keep moving (open the next
    // due deck, tier-ordered) or jump back to the daily Plan. Both are handled by
    // the desktop bridge (aqt/speedrun.py), so only offer them when pycmd works.
    function studyNext(): void {
        bridgeCommand("speedrun-study-next");
    }
    function backToPlan(): void {
        bridgeCommand("speedrun-plan");
    }

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
            <div class="bubbles" aria-hidden="true">
                {#each bubbleSeeds as b}
                    <span
                        style="left:{b.left}%; width:{b.size}px; height:{b.size}px; animation-delay:{b.delay}s; animation-duration:{b.dur}s;"
                    ></span>
                {/each}
            </div>

            <div class="brand">
                <span class="brand-mark"><BrandMark size={22} /></span>
                <span class="brand-sub">SOAP · SOA&nbsp;Exam&nbsp;P</span>
            </div>

            <p class="squeaky">Squeaky clean!</p>

            <h1>{congrats}</h1>

            <p>{nextLearnMsg}</p>

            {#if info.reviewRemaining}
                <p>{today_reviews}</p>
            {/if}

            {#if info.newRemaining}
                <p>{today_new}</p>
            {/if}

            {#if info.bridgeCommandsSupported}
                <div class="sr-actions">
                    <button
                        class="sr-btn sr-btn-primary"
                        on:click={studyNext}
                    >
                        Study next&nbsp;&rarr;
                    </button>
                    <button class="sr-btn" on:click={backToPlan}>
                        Back to plan
                    </button>
                </div>
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
        position: relative;
        overflow: hidden;

        /* A fresh "you finished" card — a mint top accent marks the win
           (inset shadow so it tucks into the rounded corners). */
        background-color: var(--canvas-elevated);
        border: 1px solid var(--border);
        border-radius: var(--sr-radius);
        padding: 2.25rem 2rem 2.5rem;
        box-shadow:
            inset 0 3px 0 0 var(--sr-mastered),
            var(--sr-shadow);

        :global(a) {
            color: var(--sr-accent);
            font-weight: 700;
            text-decoration: none;
        }
        :global(a:hover) {
            text-decoration: underline;
        }
    }

    /* Lift the real content above the decorative bubble layer. */
    .brand,
    .squeaky,
    h1,
    .congrats > p,
    .sr-actions,
    .description {
        position: relative;
        z-index: 1;
    }

    /* Rising soap bubbles (decorative; reduced-motion halts them globally). */
    .bubbles {
        position: absolute;
        inset: 0;
        z-index: 0;
        pointer-events: none;
        overflow: hidden;
    }
    .bubbles span {
        position: absolute;
        bottom: -28px;
        border-radius: 50%;
        background: radial-gradient(
            circle at 34% 30%,
            rgba(255, 255, 255, 0.9),
            var(--sr-accent) 72%
        );
        opacity: 0;
        animation-name: sr-rise;
        animation-timing-function: ease-in;
        animation-iteration-count: infinite;
    }
    @keyframes sr-rise {
        0% {
            transform: translateY(0) scale(0.7);
            opacity: 0;
        }
        14% {
            opacity: 0.42;
        }
        100% {
            transform: translateY(-360px) scale(1.05);
            opacity: 0;
        }
    }

    .squeaky {
        font-family: var(--sr-font-heading);
        font-weight: 700;
        font-size: 0.82rem;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: var(--sr-mastered);
        margin: 0 0 0.4rem;
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
        border-radius: var(--sr-radius-sm);
        background: linear-gradient(135deg, var(--sr-accent), var(--sr-accent-2));
        color: var(--sr-on-accent);
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

    /* End-of-deck navigation: keep going, or head back to the plan. */
    .sr-actions {
        display: flex;
        flex-wrap: wrap;
        gap: 0.6rem;
        justify-content: center;
        margin: 1.5rem 0 0.25rem;
    }
    .sr-btn {
        appearance: none;
        cursor: pointer;
        font-family: var(--sr-font-body, sans-serif);
        font-size: 0.95rem;
        font-weight: 700;
        padding: 0.6rem 1.15rem;
        border-radius: var(--sr-radius-sm, 8px);
        border: 1px solid var(--border);
        background: var(--canvas);
        color: var(--fg);
        transition:
            background 0.12s ease,
            border-color 0.12s ease,
            transform 0.05s ease;
    }
    .sr-btn:hover {
        border-color: var(--sr-accent);
        color: var(--sr-accent);
    }
    .sr-btn:active {
        transform: translateY(1px);
    }
    .sr-btn-primary {
        background:
            linear-gradient(
                180deg,
                rgba(255, 255, 255, 0.22),
                rgba(255, 255, 255, 0) 46%
            ),
            var(--sr-accent-strong);
        border-color: transparent;
        color: var(--sr-on-accent);
        box-shadow:
            var(--sr-shadow-sm),
            inset 0 1px 0 rgba(255, 255, 255, 0.28);
    }
    .sr-btn-primary:hover {
        background:
            linear-gradient(
                180deg,
                rgba(255, 255, 255, 0.26),
                rgba(255, 255, 255, 0) 48%
            ),
            var(--sr-accent-strong-2);
        color: var(--sr-on-accent);
    }
</style>
