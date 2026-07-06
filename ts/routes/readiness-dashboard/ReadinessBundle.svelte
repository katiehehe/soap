<!--
Copyright: Ankitects Pty Ltd and contributors
License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
-->
<script lang="ts">
    import type { ReadinessResult } from "@generated/anki/speedrun_pb";
    import { subtopicTag, TAXONOMY } from "../study-map/lib";

    // The full honesty bundle in one reusable place, so the readiness dashboard
    // and the study-map banner render the EXACT same required fields from the
    // same result (nothing about the bundle changes between views). Every field
    // the display contract requires is listed here; when readiness is withheld
    // (noScore) each shows "N/A" rather than a fabricated value.
    export let result: ReadinessResult | null = null;

    // The readiness engine can only put the raw subtopic TAG into its
    // next-best-action sentence (the human names live in the syllabus/TAXONOMY on
    // the client, not in Rust). Swap any tag token for its name. Display only; it
    // never changes the measured number.
    const SUBTOPIC_NAME = new Map<string, string>(
        TAXONOMY.flatMap((u) =>
            u.subtopics.map(
                (s) => [subtopicTag(u.id, s.id), s.name] as [string, string],
            ),
        ),
    );
    function humanizeAction(text: string): string {
        return text.replace(
            /subtopic::[a-z0-9_]+::[a-z0-9_]+/gi,
            (tag) => SUBTOPIC_NAME.get(tag) ?? tag,
        );
    }
    function pct(x: number): string {
        return `${Math.round(x * 100)}%`;
    }

    $: noScore = result?.value.case === "noScore" ? result.value.value : null;
    $: score = result?.value.case === "score" ? result.value.value : null;
    $: coveragePct = noScore?.coveragePct ?? score?.coveragePct ?? 0;
    $: gradedReviews = noScore?.gradedReviews ?? 0;
    $: nextAction = humanizeAction(
        noScore?.nextBestAction ?? score?.nextBestAction ?? "N/A",
    );
</script>

<dl class="bundle">
    <div>
        <dt>Point estimate</dt>
        <dd>{score ? score.point.toFixed(1) : "N/A"}</dd>
    </div>
    <div>
        <dt>Likely range</dt>
        <dd>
            {score ? `${score.low.toFixed(1)}-${score.high.toFixed(1)}` : "N/A"}
        </dd>
    </div>
    <div>
        <dt>Syllabus practiced</dt>
        <dd>{pct(coveragePct)}</dd>
    </div>
    <div>
        <dt>How sure (confidence)</dt>
        <dd>{score ? pct(score.confidence) : "N/A"}</dd>
    </div>
    <div>
        <dt>P(pass) today</dt>
        <dd>{score ? pct(score.passProbability) : "N/A"}</dd>
    </div>
    <div>
        <dt
            title="Calibration of past readiness predictions against real outcomes. It stays empty until predictions have been made and their outcomes observed; it is a metric that fills in over time, not a missing input."
        >
            How accurate past guesses were
        </dt>
        <dd>
            {#if score && score.pastAccuracy > 0}
                {pct(score.pastAccuracy)}
            {:else}
                N/A
                <span class="track-note">
                    tracked over time (populates as predictions accrue)
                </span>
            {/if}
        </dd>
    </div>
    <div>
        <dt>Graded reviews</dt>
        <dd>{gradedReviews}</dd>
    </div>
    <div>
        <dt>Last updated</dt>
        <dd>
            {score ? new Date(Number(score.updatedAt) * 1000).toLocaleString() : "N/A"}
        </dd>
    </div>
    <div>
        <dt>Main reasons</dt>
        <dd>
            {score && score.reasons.length ? score.reasons.join("; ") : "N/A"}
        </dd>
    </div>
    <div>
        <dt>Single best next action</dt>
        <dd>{nextAction}</dd>
    </div>
</dl>

<style>
    .bundle {
        margin: 0;
    }
    .bundle > div {
        display: flex;
        justify-content: space-between;
        gap: 1rem;
        padding: 0.6rem 0;
        border-bottom: 1px solid var(--border-subtle);
    }
    .bundle > div:last-child {
        border-bottom: none;
    }
    .bundle dt {
        color: var(--fg-subtle);
        font-family: var(--sr-font-body);
        font-size: 0.82rem;
        font-weight: 600;
    }
    .bundle dd {
        margin: 0;
        text-align: right;
        font-weight: 700;
        color: var(--fg);
    }
    /* Secondary hint under an N/A honesty field: makes clear the value is tracked
       over time (accrues as predictions are made), not an unmet requirement. */
    .track-note {
        display: block;
        margin-top: 0.15rem;
        font-family: var(--sr-font-body);
        font-size: 0.72rem;
        font-weight: 500;
        font-style: italic;
        color: var(--fg-subtle);
    }
</style>
