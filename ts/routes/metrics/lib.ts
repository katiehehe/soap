// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

// Thresholds + assumptions for the "How the metrics work" transparency page.
//
// These MIRROR the constants baked into the Rust engine. There is no shared
// Rust/TS constant, so the honest thing is to keep them in ONE place on the TS
// side and cite the exact engine source each mirrors, so if the engine changes a
// threshold, we change it here too. The page interpolates these rather than
// hardcoding drifted numbers in prose, so a definition can never quietly diverge
// from what the engine actually enforces.

// --- Readiness give-up rule + pass map (rslib/src/speedrun/service.rs) --------
// compute_readiness returns NoScore below BOTH review + coverage gates, and a
// readiness NUMBER additionally needs graded practice-test evidence.
export const MIN_GRADED_REVIEWS = 200;
export const MIN_COVERAGE = 0.5; // weighted syllabus coverage (fraction)
export const MIN_PRACTICE_QUESTIONS = 30; // graded practice-test questions
// SOA P is scored 0-10, pass at scaled >= 6; under the linear map (scaled ~=
// 10 x proportion correct) that is p-hat >= 0.60. A stated, recalibratable
// assumption, never tuned to flatter a result (docs/score-models.md).
export const PASS_PROPORTION = 0.6;
export const PASS_SCALED = 6;
export const SCALE_MAX = 10;

// --- Per-subtopic performance gate (rslib/src/speedrun/mastery.rs) ------------
// A subtopic reads "mastered" on the performance signal once it has at least
// MIN_PERF_QUESTIONS graded practice questions AND >= MIN_PERF_ACCURACY correct.
export const MIN_PERF_QUESTIONS = 5;
export const MIN_PERF_ACCURACY = 0.8; // "strong"

// --- 95% Wilson score interval (mirrors wilson_interval_f in service.rs) -------
// Robust for small samples, unlike the plain normal approximation, so a measured
// proportion (e.g. pooled practice-test accuracy on the Performance card) is
// always shown WITH a range, never a bare point. Pure + deterministic so it can
// be unit-tested and reused across screens. z = 1.96 for 95%; a zero total gives
// a degenerate (0, 0) rather than NaN. This mirrors the engine's band math so
// the client never invents a wider or narrower interval than the Rust source.
export function wilsonInterval(
    correct: number,
    total: number,
): { low: number; high: number } {
    if (total <= 0) {
        return { low: 0, high: 0 };
    }
    const z = 1.96;
    const n = total;
    const phat = Math.min(1, Math.max(0, correct / n));
    const z2 = z * z;
    const denom = 1 + z2 / n;
    const center = (phat + z2 / (2 * n)) / denom;
    const margin = (z / denom) * Math.sqrt((phat * (1 - phat)) / n + z2 / (4 * n * n));
    return {
        low: Math.min(1, Math.max(0, center - margin)),
        high: Math.min(1, Math.max(0, center + margin)),
    };
}

// The three separate signals this page documents. Never blended into one number.
export type MetricId = "memory" | "performance" | "readiness";

export const METRIC_IDS: MetricId[] = ["memory", "performance", "readiness"];

export const METRIC_LABELS: Record<MetricId, string> = {
    memory: "Memory",
    performance: "Performance",
    readiness: "Readiness",
};
