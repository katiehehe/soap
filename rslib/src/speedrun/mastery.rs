// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Topic-aware mastery model for the three-tier, mastery-gated scheduler.
//!
//! Each subtopic (tagged `subtopic::<unit>::<sub>`) is scored from real review
//! data: blocked accuracy (from the revlog) and FSRS retrievability. A subtopic
//! clears its gate, then a unit clears when all its subtopics have. That maps
//! each subtopic to a pool — Blocked, WithinUnit, CrossUnit — which drives both
//! the dashboard and the new-card ordering.

use std::collections::HashMap;

use crate::collection::Collection;
use crate::error::Result;
use crate::prelude::CardId;
use crate::prelude::DeckId;
use crate::prelude::NoteId;
use crate::scheduler::queue::DueCard;
use crate::scheduler::queue::NewCard;
use crate::timestamp::TimestampSecs;

/// Config key (string, so we don't touch upstream's `BoolKey` enum) for the
/// opt-in three-tier mastery scheduler. Default OFF: with it unset the live
/// queue is built exactly as upstream Anki builds it, which keeps the demo path
/// and the ablation's plain-Anki baseline untouched.
pub(crate) const MASTERY_SCHEDULER_KEY: &str = "speedrunMasteryScheduler";

/// Config key for the opt-in points-at-stake live review order. Default OFF.
pub(crate) const POINTS_AT_STAKE_KEY: &str = "speedrunPointsAtStake";

/// Config key holding the per-subtopic importance weights (a JSON object,
/// subtopic tag -> weight) that Python writes from the topic map, so the live
/// review reorder can weight by exam importance. Absent -> equal weighting
/// (weakest-topic-first).
pub(crate) const SUBTOPIC_WEIGHTS_KEY: &str = "speedrunSubtopicWeights";

/// Config key for the study-feature ABLATION (brief 8, build 2). When on (and
/// the mastery scheduler is on), the within-unit interleaving tier is removed:
/// a cleared subtopic drops straight into one global mixed pool instead of its
/// unit's within-unit pool. Default off. This is the single flag that turns the
/// full three-tier scheduler (build 1) into the ablated build (build 2); build
/// 3 is plain Anki (mastery scheduler off).
pub(crate) const ABLATE_WITHIN_UNIT_KEY: &str = "speedrunAblateWithinUnit";

/// Config key for the transient "active tier scope": when the user opens a
/// within-unit or cross-unit TIER deck from the study map/plan, Python writes
/// `{deck_id, tier}` here so the queue builder serves ONLY the subtopics that
/// are actually in that tier's mastery pool. Without it a parent (unit/root)
/// deck studies its whole subtree — so a still-Blocked subtopic would leak into
/// within-/cross-unit study. The scope is keyed to the deck it was set for, so a
/// stale value never affects a different deck; absent -> no scoping (the deck is
/// studied exactly as upstream builds it). Mirrors the practice-deck scoping in
/// `qt/aqt/speedrun.py`, but at the queue level so FSRS still schedules normally
/// (no filtered deck). See `speedrun_scope_queues_to_tier`.
pub(crate) const ACTIVE_TIER_SCOPE_KEY: &str = "speedrunActiveTierScope";

/// Config key holding the target exam date as a unix timestamp (local noon of
/// the exam day; noon so day-counting is robust to timezones / Anki's day
/// rollover). Written by Python from the study map's date picker. Absent -> no
/// pace is shown (we never invent a deadline).
pub(crate) const EXAM_DATE_KEY: &str = "speedrunExamDate";

/// Config key: guided-learning mode (the hard prerequisite gate). Unlike the
/// other speedrun scheduler flags, this defaults ON — a fresh learner is guided
/// through the curriculum order. Turning it off is the experienced-user "free
/// mode" bypass. Either way the gate is only a read-only new-card filter, so
/// undo and collection integrity are untouched.
pub(crate) const GUIDED_MODE_KEY: &str = "speedrunGuidedMode";

/// Config key: subtopic tags the user has explicitly unlocked (a per-topic
/// bypass of the guided gate). A JSON list of tags; empty by default.
pub(crate) const UNLOCKED_SUBTOPICS_KEY: &str = "speedrunUnlockedSubtopics";

/// Config key: per-subtopic practice-test performance ({tag: {questions,
/// correct}}), written by Python's `practice_test.record_test`. A SEPARATE
/// signal from the memory gate: it can satisfy a prerequisite, but it never
/// changes the memory gate itself.
pub(crate) const PERFORMANCE_KEY: &str = "speedrunPerformanceBySubtopic";

/// Config keys: the guided-learning DAG, written by Python from the topic map.
/// Subtopic edges ({tag: [prereq tags]}) and unit edges ({unit: [prereq
/// units]}). Curriculum ordering only; never affects the give-up thresholds.
pub(crate) const SUBTOPIC_PREREQS_KEY: &str = "speedrunSubtopicPrereqs";
pub(crate) const UNIT_PREREQS_KEY: &str = "speedrunUnitPrereqs";

/// Pre-registered gate (PRD 8): a subtopic clears when it has been executed
/// enough times, accurately, and its memory is strong.
pub(crate) const MIN_PROBLEMS: u32 = 10;
pub(crate) const MIN_ACCURACY: f64 = 0.80;
pub(crate) const MIN_RETRIEVABILITY: f64 = 0.90;

/// Performance gate (SEPARATE from the memory gate): a subtopic is
/// "performance-mastered" with enough graded practice-test questions AND high
/// enough accuracy. Below the sample floor it abstains (stays false) rather
/// than inventing a number, so a couple of lucky answers can't unlock the tree.
pub(crate) const MIN_PERF_QUESTIONS: u32 = 5;
pub(crate) const MIN_PERF_ACCURACY: f64 = 0.80;

/// A unit's within-unit interleaving tier only activates once at least this
/// many of its subtopics have cleared their gate: with fewer, there is nothing
/// to interleave *against*, so a single cleared subtopic keeps practicing in
/// isolation (the blocked tier) rather than being mislabeled as "within-unit
/// interleaving". This is the ONE source of truth for when within-unit begins —
/// `compute_pools` (the card banner + queue order), `recommend_study`, and
/// `build_study_plan` all read it, so they can never drift apart again (a lone
/// cleared subtopic showing up as within-unit on one surface and blocked on
/// another was exactly the reported bug).
pub(crate) const MIN_CLEARED_TO_INTERLEAVE: u32 = 2;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Pool {
    /// Not yet mastered — practice this subtopic in isolation.
    Blocked,
    /// Cleared, but its unit isn't fully mastered — interleave within the unit.
    WithinUnit,
    /// Its unit is mastered — interleave across units (spacing).
    CrossUnit,
}

/// Which mastery TIER a study session is scoped to (the strict-tier study). A
/// unit deck opens the within-unit tier; the root deck opens the cross-unit
/// tier. Blocked practice needs no scope (a subtopic/leaf deck already holds one
/// subtopic), so it is intentionally absent here. Parsed from the transient
/// `speedrunActiveTierScope` config.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum TierScope {
    WithinUnit,
    CrossUnit,
}

impl TierScope {
    /// The config `tier` string Python writes (kept in one place so both sides
    /// agree). Unknown strings parse to `None`, so a malformed scope is ignored
    /// rather than mis-filtering the queue.
    fn from_config_str(s: &str) -> Option<Self> {
        match s {
            "within_unit" => Some(TierScope::WithinUnit),
            "cross_unit" => Some(TierScope::CrossUnit),
            _ => None,
        }
    }
}

/// Whether a subtopic in `pool` is eligible to be SERVED when studying `tier`.
/// This is the strict-tier rule: within-unit study serves only WithinUnit-pool
/// subtopics; cross-unit study serves only CrossUnit-pool subtopics. A
/// still-Blocked subtopic is eligible for NEITHER, so it can never leak into a
/// parent-deck (unit/root) study session. Pure, so it is directly unit-testable.
pub(crate) fn pool_eligible_for_tier(pool: Pool, tier: TierScope) -> bool {
    match tier {
        TierScope::WithinUnit => matches!(pool, Pool::WithinUnit),
        TierScope::CrossUnit => matches!(pool, Pool::CrossUnit),
    }
}

/// Per-subtopic review stats, accumulated from the collection.
#[derive(Debug, Clone, Default)]
pub(crate) struct SubtopicStats {
    pub unit_id: String,
    pub subtopic_id: String,
    pub reviews: u32,
    pub correct: u32,
    pub retr_sum: f64,
    pub retr_count: u32,
    /// Per-reviewed-card FSRS retrievability, kept so we can report a MEASURED
    /// recall band (percentiles) alongside the mean, not just a point.
    pub retr_values: Vec<f64>,
    /// Relative importance weight from the topic map (0 when none supplied).
    /// Set by the caller from the request; used only for the weighted rollup.
    pub weight: f64,
    /// Practice-test PERFORMANCE for this subtopic (a SEPARATE signal from the
    /// memory gate). Set by the caller from config; used only to decide FULL
    /// mastery (memory gate AND performance) — never folded into memory accuracy
    /// or retrievability.
    pub performance: Performance,
}

impl SubtopicStats {
    pub(crate) fn new(unit_id: &str, subtopic_id: &str) -> Self {
        Self {
            unit_id: unit_id.to_string(),
            subtopic_id: subtopic_id.to_string(),
            ..Default::default()
        }
    }

    pub(crate) fn tag(&self) -> String {
        format!("subtopic::{}::{}", self.unit_id, self.subtopic_id)
    }

    pub(crate) fn accuracy(&self) -> f64 {
        if self.reviews == 0 {
            0.0
        } else {
            self.correct as f64 / self.reviews as f64
        }
    }

    pub(crate) fn mean_retrievability(&self) -> f64 {
        if self.retr_count == 0 {
            0.0
        } else {
            self.retr_sum / self.retr_count as f64
        }
    }

    /// (low, high) = 10th/90th percentile of this subtopic's reviewed-card
    /// retrievability, so the memory signal carries a MEASURED range, not just
    /// a mean. (0.0, 0.0) when the subtopic has no reviewed cards.
    pub(crate) fn recall_band(&self) -> (f64, f64) {
        percentile_band(&self.retr_values)
    }

    /// The subtopic MEMORY gate: enough graded problems, accurate, and
    /// well-retained. This drives flashcard-scheduling tiers and the memory
    /// signal; FULL mastery additionally requires performance (see
    /// `fully_mastered`).
    pub(crate) fn gate_cleared(&self) -> bool {
        self.reviews >= MIN_PROBLEMS
            && self.accuracy() >= MIN_ACCURACY
            && self.mean_retrievability() >= MIN_RETRIEVABILITY
    }

    /// FULL mastery: the memory gate is cleared AND practice-test PERFORMANCE is
    /// mastered — you can both RECALL the fact and SOLVE exam-style problems with
    /// it. This is the "done" bar the Overall-mastery rollups and the mastery
    /// pace burn down to. Memory and Performance stay SEPARATE signals (each
    /// shown with its own range); this only ANDs their two gates, it never
    /// averages them into one blended score.
    pub(crate) fn fully_mastered(&self) -> bool {
        self.gate_cleared() && self.performance.mastered()
    }
}

/// The 10th and 90th percentiles of a set of values (linear interpolation
/// between ranks). Returns (0.0, 0.0) for an empty slice. Used for the MEASURED
/// memory-recall band (per subtopic and overall).
pub(crate) fn percentile_band(values: &[f64]) -> (f64, f64) {
    if values.is_empty() {
        return (0.0, 0.0);
    }
    let mut v = values.to_vec();
    v.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    (percentile(&v, 0.10), percentile(&v, 0.90))
}

fn percentile(sorted: &[f64], p: f64) -> f64 {
    match sorted.len() {
        0 => 0.0,
        1 => sorted[0],
        n => {
            let rank = p * (n as f64 - 1.0);
            let lo = rank.floor() as usize;
            let hi = rank.ceil() as usize;
            if lo == hi {
                sorted[lo]
            } else {
                let frac = rank - lo as f64;
                sorted[lo] * (1.0 - frac) + sorted[hi] * frac
            }
        }
    }
}

/// Overall memory-recall signal across all reviewed syllabus cards.
#[derive(Debug, Clone, Default)]
pub(crate) struct MemoryRecallData {
    pub has_data: bool,
    pub point: f64,
    pub low: f64,
    pub high: f64,
    pub reviewed_cards: u32,
}

/// Mean FSRS retrievability (point) + 10th-90th percentile band over every
/// reviewed syllabus card. Abstains (`has_data = false`) when nothing has been
/// reviewed yet, so the Memory signal is never a fabricated number.
pub(crate) fn memory_recall(stats: &[SubtopicStats]) -> MemoryRecallData {
    let mut all: Vec<f64> = Vec::new();
    for s in stats {
        all.extend_from_slice(&s.retr_values);
    }
    if all.is_empty() {
        return MemoryRecallData::default();
    }
    let point = all.iter().sum::<f64>() / all.len() as f64;
    let (low, high) = percentile_band(&all);
    MemoryRecallData {
        has_data: true,
        point,
        low,
        high,
        reviewed_cards: all.len() as u32,
    }
}

/// Per-subtopic practice-test performance: accuracy over graded exam-style
/// questions. A SEPARATE measure from the memory gate above — the two never
/// blend (kept apart per the rubric's three-separate-scores rule). It can
/// satisfy a prerequisite in the guided DAG, but it never moves the memory
/// gate.
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub(crate) struct Performance {
    pub questions: u32,
    pub correct: u32,
}

impl Performance {
    pub(crate) fn accuracy(&self) -> f64 {
        if self.questions == 0 {
            0.0
        } else {
            self.correct as f64 / self.questions as f64
        }
    }

    /// Performance-mastered: enough graded practice questions AND accurate.
    /// Abstains (false) below the sample floor, so it never fabricates mastery.
    pub(crate) fn mastered(&self) -> bool {
        self.questions >= MIN_PERF_QUESTIONS && self.accuracy() >= MIN_PERF_ACCURACY
    }
}

/// Parse a `subtopic::<unit>::<sub>` tag into (unit, subtopic).
pub(crate) fn parse_subtopic_tag(tag: &str) -> Option<(String, String)> {
    let rest = tag.strip_prefix("subtopic::")?;
    let (unit, sub) = rest.split_once("::")?;
    if unit.is_empty() || sub.is_empty() {
        None
    } else {
        Some((unit.to_string(), sub.to_string()))
    }
}

/// Multi-level gating: a subtopic's pool depends on its own gate, how many of
/// its unit's sub-types have cleared (you can only *interleave within a unit*
/// once there are >= MIN_CLEARED_TO_INTERLEAVE cleared sub-types to mix), and
/// whether its whole unit has been mastered (every subtopic cleared).
///
/// A cleared subtopic whose unit has fewer than MIN_CLEARED_TO_INTERLEAVE
/// cleared sub-types stays in the **Blocked** tier: with nothing to interleave
/// against, "within-unit interleaving" would just be blocked practice of one
/// subtopic wearing the wrong label. It promotes to WithinUnit the moment a
/// sibling clears. This keeps the pool (which drives the review banner and the
/// live queue order) consistent with `recommend_study` and `build_study_plan`,
/// which already require >= MIN_CLEARED_TO_INTERLEAVE cleared for the tier.
pub(crate) fn compute_pools(stats: &[SubtopicStats]) -> HashMap<String, Pool> {
    // A unit is mastered only if it has >= 1 subtopic and all are cleared.
    let mut unit_total: HashMap<&str, u32> = HashMap::new();
    let mut unit_cleared: HashMap<&str, u32> = HashMap::new();
    for s in stats {
        *unit_total.entry(s.unit_id.as_str()).or_default() += 1;
        if s.gate_cleared() {
            *unit_cleared.entry(s.unit_id.as_str()).or_default() += 1;
        }
    }
    let unit_mastered = |unit: &str| -> bool {
        let total = unit_total.get(unit).copied().unwrap_or(0);
        total > 0 && unit_cleared.get(unit).copied().unwrap_or(0) == total
    };

    stats
        .iter()
        .map(|s| {
            let cleared_in_unit = unit_cleared.get(s.unit_id.as_str()).copied().unwrap_or(0);
            let pool = if !s.gate_cleared() {
                // Not yet mastered: drill this subtopic in isolation.
                Pool::Blocked
            } else if unit_mastered(&s.unit_id) {
                // Whole unit cleared: interleave across units (spacing).
                Pool::CrossUnit
            } else if cleared_in_unit >= MIN_CLEARED_TO_INTERLEAVE {
                // Unit not fully mastered but has >= 2 cleared sub-types to
                // interleave against -> genuine within-unit interleaving.
                Pool::WithinUnit
            } else {
                // Cleared, but the ONLY cleared sub-type in its unit: nothing to
                // interleave yet, so keep practicing it in isolation until a
                // sibling clears (honest blocked tier, not a mislabeled mix).
                Pool::Blocked
            };
            (s.tag(), pool)
        })
        .collect()
}

/// The guided-gate state of one subtopic: whether its new cards are withheld,
/// and which prerequisites are not yet satisfied (for the lock reason on the
/// map). Curriculum ordering only — it never affects any score or the give-up
/// rule.
#[derive(Debug, Clone, Default, PartialEq)]
pub(crate) struct LockState {
    pub locked: bool,
    pub unmet_prereqs: Vec<String>,
}

/// A prerequisite is satisfied when its MEMORY gate is cleared OR its
/// practice-test PERFORMANCE is mastered — so an experienced learner can unlock
/// downstream topics by testing well, without flashcard reps. The two signals
/// stay separate; this only ORs them for the gate decision.
fn prereq_satisfied(
    tag: &str,
    started: &HashMap<String, bool>,
    gate: &HashMap<String, bool>,
    perf: &HashMap<String, Performance>,
) -> bool {
    // Unknown prereq (not among the syllabus stats): fail OPEN so a data gap
    // can't permanently lock the tree. Known prereqs must actually be satisfied.
    if !gate.contains_key(tag) {
        return true;
    }
    // Softened guided gate: a prerequisite counts as satisfied once you've
    // STARTED it (studied it at all — "in progress"), not only when it is fully
    // mastered. Full mastery and a passed practice test still satisfy it. This
    // keeps the guided ORDER (roots first, then their dependents) without forcing
    // full mastery of each step before the next opens, so FSRS spacing out a
    // topic's reviews never leaves the learner with nothing new to do.
    started.get(tag).copied().unwrap_or(false)
        || gate.get(tag).copied().unwrap_or(false)
        || perf.get(tag).map(|p| p.mastered()).unwrap_or(false)
}

/// Compute the guided-learning lock for every subtopic. A subtopic is locked
/// when guided mode is on, it isn't explicitly unlocked, and some prerequisite
/// is unmet — either a direct subtopic prereq, or (via unit prereqs) a whole
/// upstream unit that isn't finished. `unmet_prereqs` is always populated (even
/// in free mode) so the UI can show the recommended order; only `locked`
/// respects the guided flag + per-topic unlocks. Pure (no I/O), so it is fully
/// unit-testable and never touches the collection.
pub(crate) fn compute_locks(
    stats: &[SubtopicStats],
    perf: &HashMap<String, Performance>,
    subtopic_prereqs: &HashMap<String, Vec<String>>,
    unit_prereqs: &HashMap<String, Vec<String>>,
    unlocked: &std::collections::HashSet<String>,
    guided: bool,
) -> HashMap<String, LockState> {
    // Memory-gate state per subtopic tag.
    let gate: HashMap<String, bool> = stats.iter().map(|s| (s.tag(), s.gate_cleared())).collect();
    // "Started" state per subtopic tag: has it been studied at all? A prereq is
    // satisfied once it's in progress (not only when mastered), so the guided
    // order never forces full mastery of each step before the next unlocks.
    let started: HashMap<String, bool> = stats.iter().map(|s| (s.tag(), s.reviews > 0)).collect();

    // Subtopics grouped by unit, for whole-unit satisfaction.
    let mut unit_subs: HashMap<String, Vec<String>> = HashMap::new();
    for s in stats {
        unit_subs
            .entry(s.unit_id.clone())
            .or_default()
            .push(s.tag());
    }
    // A unit counts as satisfied (as a prereq for a downstream unit) only when
    // ALL of its subtopics are prereq-satisfied — "master univariate before
    // multivariate". An unknown/empty unit imposes no gate.
    let unit_satisfied = |unit: &str| -> bool {
        match unit_subs.get(unit) {
            Some(tags) if !tags.is_empty() => tags
                .iter()
                .all(|t| prereq_satisfied(t, &started, &gate, perf)),
            _ => true,
        }
    };
    // A representative not-yet-satisfied subtopic of a unit, for the lock reason.
    let unit_blocker = |unit: &str| -> Option<String> {
        unit_subs
            .get(unit)?
            .iter()
            .find(|t| !prereq_satisfied(t, &started, &gate, perf))
            .cloned()
    };

    stats
        .iter()
        .map(|s| {
            let tag = s.tag();
            let mut unmet: Vec<String> = Vec::new();
            // Direct subtopic prerequisites.
            if let Some(ps) = subtopic_prereqs.get(&tag) {
                for p in ps {
                    if !prereq_satisfied(p, &started, &gate, perf) {
                        unmet.push(p.clone());
                    }
                }
            }
            // Cross-unit prerequisites: each upstream unit must be finished.
            if let Some(us) = unit_prereqs.get(&s.unit_id) {
                for u in us {
                    if !unit_satisfied(u) {
                        if let Some(b) = unit_blocker(u) {
                            if !unmet.contains(&b) {
                                unmet.push(b);
                            }
                        }
                    }
                }
            }
            let locked = guided && !unlocked.contains(&tag) && !unmet.is_empty();
            (
                tag,
                LockState {
                    locked,
                    unmet_prereqs: unmet,
                },
            )
        })
        .collect()
}

/// Honest, measured rollup of the mastery gate across the whole syllabus. Every
/// field is a count of demonstrated state, never a predicted score.
/// `mastered` + `in_progress` + `not_started` always equals `subtopics_total`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub(crate) struct MasteryOverallCounts {
    pub subtopics_total: u32,
    pub subtopics_mastered: u32,
    pub subtopics_in_progress: u32,
    pub subtopics_not_started: u32,
    pub units_total: u32,
    pub units_mastered: u32,
    pub total_reviews: u32,
}

/// Roll up per-subtopic stats into honest overall counts. A subtopic is
/// `not_started` with zero reviews, `mastered` once it is FULLY mastered (memory
/// gate cleared AND practice-test performance mastered), and `in_progress`
/// otherwise; the three partition the syllabus so nothing is double-counted or
/// invented. A unit is mastered when it has >= 1 subtopic and all are fully
/// mastered. (Callers must attach each stat's `performance`; unset performance
/// counts as not-yet-mastered.)
pub(crate) fn mastery_overall(stats: &[SubtopicStats]) -> MasteryOverallCounts {
    let subtopics_total = stats.len() as u32;
    let subtopics_mastered = stats.iter().filter(|s| s.fully_mastered()).count() as u32;
    let subtopics_not_started = stats.iter().filter(|s| s.reviews == 0).count() as u32;
    let subtopics_in_progress = subtopics_total
        .saturating_sub(subtopics_mastered)
        .saturating_sub(subtopics_not_started);

    let mut unit_total: HashMap<&str, u32> = HashMap::new();
    let mut unit_cleared: HashMap<&str, u32> = HashMap::new();
    for s in stats {
        *unit_total.entry(s.unit_id.as_str()).or_default() += 1;
        if s.fully_mastered() {
            *unit_cleared.entry(s.unit_id.as_str()).or_default() += 1;
        }
    }
    let units_mastered = unit_total
        .iter()
        .filter(|(u, &tot)| tot > 0 && unit_cleared.get(*u).copied().unwrap_or(0) == tot)
        .count() as u32;

    MasteryOverallCounts {
        subtopics_total,
        subtopics_mastered,
        subtopics_in_progress,
        subtopics_not_started,
        units_total: unit_total.len() as u32,
        units_mastered,
        total_reviews: stats.iter().map(|s| s.reviews).sum(),
    }
}

/// Importance-weighted mastery rollup. `overall_pct` and each unit's pct are
/// the share of that group's total weight that sits on FULLY-mastered subtopics
/// (memory gate cleared AND practice-test performance mastered). When no weights
/// are supplied (total weight 0) it falls back to the plain mastered/total count
/// fraction, so a caller that omits weights still gets a sensible number. Every
/// value is MEASURED demonstrated mastery, never a predicted score. (Callers must
/// attach each stat's `performance`.)
#[derive(Debug, Clone, Default, PartialEq)]
pub(crate) struct WeightedMastery {
    pub overall_pct: f64,
    pub overall_weight: f64,
    /// unit_id -> weighted mastery fraction (0..1)
    pub per_unit_pct: HashMap<String, f64>,
    /// unit_id -> sum of the unit's subtopic weights (its importance)
    pub per_unit_weight: HashMap<String, f64>,
}

pub(crate) fn weighted_mastery(stats: &[SubtopicStats]) -> WeightedMastery {
    let mut unit_weight: HashMap<String, f64> = HashMap::new();
    let mut unit_cleared_weight: HashMap<String, f64> = HashMap::new();
    let mut unit_total: HashMap<String, u32> = HashMap::new();
    let mut unit_cleared_count: HashMap<String, u32> = HashMap::new();
    for s in stats {
        let cleared = s.fully_mastered();
        *unit_weight.entry(s.unit_id.clone()).or_default() += s.weight;
        *unit_total.entry(s.unit_id.clone()).or_default() += 1;
        if cleared {
            *unit_cleared_weight.entry(s.unit_id.clone()).or_default() += s.weight;
            *unit_cleared_count.entry(s.unit_id.clone()).or_default() += 1;
        }
    }

    let frac = |cleared_w: f64, total_w: f64, cleared_n: u32, total_n: u32| -> f64 {
        if total_w > 0.0 {
            cleared_w / total_w
        } else if total_n > 0 {
            cleared_n as f64 / total_n as f64
        } else {
            0.0
        }
    };

    let per_unit_pct = unit_weight
        .keys()
        .map(|unit| {
            let pct = frac(
                unit_cleared_weight.get(unit).copied().unwrap_or(0.0),
                unit_weight.get(unit).copied().unwrap_or(0.0),
                unit_cleared_count.get(unit).copied().unwrap_or(0),
                unit_total.get(unit).copied().unwrap_or(0),
            );
            (unit.clone(), pct)
        })
        .collect();

    let overall_weight: f64 = stats.iter().map(|s| s.weight).sum();
    let cleared_weight: f64 = stats
        .iter()
        .filter(|s| s.fully_mastered())
        .map(|s| s.weight)
        .sum();
    let total_n = stats.len() as u32;
    let cleared_n = stats.iter().filter(|s| s.fully_mastered()).count() as u32;
    let overall_pct = frac(cleared_weight, overall_weight, cleared_n, total_n);

    WeightedMastery {
        overall_pct,
        overall_weight,
        per_unit_pct,
        per_unit_weight: unit_weight,
    }
}

/// A ranked "what to study next" suggestion.
#[derive(Debug, Clone, PartialEq)]
pub(crate) struct StudyPriorityItem {
    pub tag: String,
    pub unit_id: String,
    pub subtopic_id: String,
    pub weight: f64,
    pub score: f64,
    pub reason: String,
}

/// How much studying a subtopic can still move the needle, in [0, 1]. A cleared
/// gate is 0 (done); a never-started subtopic is 1 (full opportunity, and it
/// also grows coverage); a partially-studied one is the honest distance to its
/// gate. Purely a function of MEASURED review state.
fn opportunity(s: &SubtopicStats) -> f64 {
    if s.gate_cleared() {
        0.0
    } else if s.reviews == 0 {
        1.0
    } else if s.reviews < MIN_PROBLEMS {
        // Started, but not enough evidence to judge accuracy/retention yet.
        0.8
    } else {
        // Judgeable: how far below the accuracy/retention gate we still sit.
        let acc = (s.accuracy() / MIN_ACCURACY).min(1.0);
        let retr = (s.mean_retrievability() / MIN_RETRIEVABILITY).min(1.0);
        (1.0 - acc.min(retr)).max(0.1)
    }
}

fn priority_reason(s: &SubtopicStats) -> String {
    if s.reviews == 0 {
        "Not studied yet — start here to cover a high-weight subtopic.".to_string()
    } else if s.reviews < MIN_PROBLEMS {
        format!(
            "Only {}/{} graded reviews — keep practicing to build enough evidence.",
            s.reviews, MIN_PROBLEMS
        )
    } else {
        "Reviewed but not yet mastered — push accuracy to 80% and retention to 90%.".to_string()
    }
}

/// Rank the subtopics still worth studying, highest impact first: importance
/// weight times remaining opportunity. Cleared subtopics drop out. With no
/// weights supplied, every subtopic is treated as equally weighted so the
/// ranking still reflects opportunity. Ties keep the input (syllabus) order, so
/// the output is deterministic. This only reorders measured state by exam
/// importance; it never fabricates a score.
pub(crate) fn study_priorities(stats: &[SubtopicStats]) -> Vec<StudyPriorityItem> {
    let use_equal = stats.iter().map(|s| s.weight).sum::<f64>() <= 0.0;
    let mut items: Vec<StudyPriorityItem> = stats
        .iter()
        .filter(|s| !s.gate_cleared())
        .map(|s| {
            let w = if use_equal { 1.0 } else { s.weight };
            StudyPriorityItem {
                tag: s.tag(),
                unit_id: s.unit_id.clone(),
                subtopic_id: s.subtopic_id.clone(),
                weight: s.weight,
                score: w * opportunity(s),
                reason: priority_reason(s),
            }
        })
        .collect();
    items.sort_by(|a, b| {
        b.score
            .partial_cmp(&a.score)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    items
}

/// The tier of practice to recommend next.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum StudyMode {
    Blocked,
    WithinUnit,
    CrossUnit,
    AllMastered,
}

/// The recommended next study action, so practice progresses through the tiers
/// instead of staying blocked: block the weakest uncleared subtopic, then once
/// a unit has >= 2 cleared sub-types interleave that unit, and once everything
/// is cleared review across units. Purely a function of the measured gate
/// state.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct StudyRec {
    pub mode: StudyMode,
    pub subtopic_tag: Option<String>,
    pub unit_id: Option<String>,
}

pub(crate) fn recommend_study(stats: &[SubtopicStats]) -> StudyRec {
    let none = StudyRec {
        mode: StudyMode::AllMastered,
        subtopic_tag: None,
        unit_id: None,
    };
    if stats.is_empty() {
        return none;
    }
    // Everything cleared -> interleave across units.
    if stats.iter().all(|s| s.gate_cleared()) {
        return StudyRec {
            mode: StudyMode::CrossUnit,
            ..none
        };
    }
    // A unit with >= 2 cleared sub-types (enough to interleave) that isn't fully
    // mastered -> recommend within-unit interleaving of that unit. Pick the most
    // cleared such unit, in first-seen order for determinism.
    let mut order: Vec<String> = Vec::new();
    let mut total: HashMap<String, u32> = HashMap::new();
    let mut cleared: HashMap<String, u32> = HashMap::new();
    for s in stats {
        if !total.contains_key(&s.unit_id) {
            order.push(s.unit_id.clone());
        }
        *total.entry(s.unit_id.clone()).or_default() += 1;
        if s.gate_cleared() {
            *cleared.entry(s.unit_id.clone()).or_default() += 1;
        }
    }
    let mut best: Option<(&str, u32)> = None;
    for u in &order {
        let c = cleared.get(u).copied().unwrap_or(0);
        let t = total.get(u).copied().unwrap_or(0);
        if c >= MIN_CLEARED_TO_INTERLEAVE && c < t && best.map_or(true, |(_, bc)| c > bc) {
            best = Some((u.as_str(), c));
        }
    }
    if let Some((u, _)) = best {
        return StudyRec {
            mode: StudyMode::WithinUnit,
            subtopic_tag: None,
            unit_id: Some(u.to_string()),
        };
    }
    // Otherwise block the highest-priority uncleared subtopic (procedure first).
    if let Some(top) = study_priorities(stats).into_iter().next() {
        return StudyRec {
            mode: StudyMode::Blocked,
            subtopic_tag: Some(top.tag),
            unit_id: None,
        };
    }
    none
}

/// One deck in the tiered "today" study plan, decoupled from proto so the
/// tiering + actionable filter can be unit-tested without a live collection.
/// Counts are today's real (daily-limit capped) deck-tree numbers.
#[derive(Debug, Clone, PartialEq)]
pub(crate) struct PlanItem {
    pub tier: StudyMode,
    pub deck_id: i64,
    pub subtopic_tag: Option<String>,
    pub unit_id: Option<String>,
    pub new: u32,
    pub review: u32,
    pub learn: u32,
    pub total: u32,
}

/// Deck counts tuple `(new, review, learn, total_including_children)`.
type Counts = (u32, u32, u32, u32);

fn is_actionable(c: Counts) -> bool {
    c.0 + c.1 + c.2 > 0
}

/// Sum today's `(new, review, learn, total)` across a set of subtopics, reading
/// each subtopic's OWN (leaf) deck counts. A parent-tier row (within-/cross-unit)
/// uses this so it reflects exactly the cards STRICT-study serves for that tier —
/// only the in-pool subtopics — instead of the parent deck's rolled-up total,
/// which would also count the tier's out-of-pool (e.g. still-blocked) subtopics.
fn sum_subtopic_counts<'a>(
    tags: impl IntoIterator<Item = &'a str>,
    tag_deck: &HashMap<String, i64>,
    counts: &HashMap<i64, Counts>,
) -> Counts {
    let mut acc: Counts = (0, 0, 0, 0);
    for tag in tags {
        if let Some(&did) = tag_deck.get(tag) {
            if let Some(&c) = counts.get(&did) {
                acc.0 += c.0;
                acc.1 += c.1;
                acc.2 += c.2;
                acc.3 += c.3;
            }
        }
    }
    acc
}

/// Build today's tiered study plan from measured gate state + real deck counts.
///
/// - BLOCKED: every uncleared subtopic (highest exam-importance first),
///   pointing at its own subtopic deck — drill it in isolation.
/// - WITHIN_UNIT: units with WithinUnit-pool sub-types to interleave, pointing
///   at the unit deck (the parent of its subtopic decks). Its counts sum ONLY
///   those in-pool subtopics — matching what strict-study serves — not the unit
///   deck's rolled-up total (which would also count the unit's still-blocked
///   subtopics: the reported 6-not-12 bug).
/// - CROSS_UNIT: the CrossUnit-pool subtopics (units that are fully mastered),
///   pointing at the whole-exam deck (the grandparent of a subtopic deck) for
///   cross-unit spacing. Its counts sum ONLY those subtopics, not the root
///   deck's rolled-up total.
///
/// Tier membership is read from `pools` (via `pool_eligible_for_tier`), the SAME
/// predicate the live strict queue (`scope_cards_to_tier`) uses, so the plan
/// counts and what the queue serves can never drift apart.
///
/// Only decks with something due today are returned (`is_actionable`). Pure: it
/// reorders/labels measured state and never fabricates a score.
///
/// `tag_deck` maps a subtopic tag to the deck holding its cards; `counts` maps
/// a deck id to its today counts; `parent` maps a deck id to its parent (top =
/// 0).
pub(crate) fn build_study_plan(
    stats: &[SubtopicStats],
    pools: &HashMap<String, Pool>,
    tag_deck: &HashMap<String, i64>,
    counts: &HashMap<i64, Counts>,
    parent: &HashMap<i64, i64>,
) -> Vec<PlanItem> {
    let mut items: Vec<PlanItem> = Vec::new();

    // BLOCKED tier, importance order (study_priorities already drops cleared
    // subtopics and, since uncleared == Blocked pool, this is the blocked set).
    for p in study_priorities(stats) {
        if pools.get(&p.tag).copied() != Some(Pool::Blocked) {
            continue;
        }
        if let Some(&did) = tag_deck.get(&p.tag) {
            if let Some(&c) = counts.get(&did).filter(|c| is_actionable(**c)) {
                items.push(PlanItem {
                    tier: StudyMode::Blocked,
                    deck_id: did,
                    subtopic_tag: Some(p.tag.clone()),
                    unit_id: None,
                    new: c.0,
                    review: c.1,
                    learn: c.2,
                    total: c.3,
                });
            }
        }
    }

    // Per-unit, first-seen order, plus a sample subtopic deck per unit (to
    // resolve the unit / root deck ids from the deck tree). Tier membership
    // itself is read from `pools`, so the plan and the live strict queue share
    // one source of truth.
    let mut unit_order: Vec<String> = Vec::new();
    let mut seen_unit: std::collections::HashSet<String> = std::collections::HashSet::new();
    let mut sample_deck: HashMap<String, i64> = HashMap::new();
    for s in stats {
        if seen_unit.insert(s.unit_id.clone()) {
            unit_order.push(s.unit_id.clone());
        }
        if let Some(&did) = tag_deck.get(&s.tag()) {
            sample_deck.entry(s.unit_id.clone()).or_insert(did);
        }
    }

    // WITHIN_UNIT tier: a unit that has WithinUnit-pool sub-types. The row still
    // OPENS the unit deck (strict-study scopes it), but its counts sum ONLY the
    // in-pool subtopics — so a unit of 6 within-unit + 6 blocked shows 6, not the
    // unit deck's rolled-up 12.
    for unit in &unit_order {
        let in_pool: Vec<String> = stats
            .iter()
            .filter(|s| &s.unit_id == unit)
            .filter(|s| {
                pools
                    .get(&s.tag())
                    .map(|p| pool_eligible_for_tier(*p, TierScope::WithinUnit))
                    .unwrap_or(false)
            })
            .map(|s| s.tag())
            .collect();
        if in_pool.is_empty() {
            continue;
        }
        let Some(&sub_did) = sample_deck.get(unit) else {
            continue;
        };
        let unit_did = parent.get(&sub_did).copied().unwrap_or(0);
        if unit_did == 0 {
            continue;
        }
        let cc = sum_subtopic_counts(in_pool.iter().map(String::as_str), tag_deck, counts);
        if is_actionable(cc) {
            items.push(PlanItem {
                tier: StudyMode::WithinUnit,
                deck_id: unit_did,
                subtopic_tag: None,
                unit_id: Some(unit.clone()),
                new: cc.0,
                review: cc.1,
                learn: cc.2,
                total: cc.3,
            });
        }
    }

    // CROSS_UNIT tier: the CrossUnit-pool subtopics (their units are fully
    // mastered). The row OPENS the whole-exam deck (grandparent of a subtopic
    // deck), but its counts sum ONLY those CrossUnit subtopics, not the root
    // deck's rolled-up total.
    let cross_tags: Vec<String> = stats
        .iter()
        .filter(|s| {
            pools
                .get(&s.tag())
                .map(|p| pool_eligible_for_tier(*p, TierScope::CrossUnit))
                .unwrap_or(false)
        })
        .map(|s| s.tag())
        .collect();
    if !cross_tags.is_empty() {
        // All subtopics share one root, so any subtopic deck resolves it.
        let root = sample_deck.values().next().map(|&sub_did| {
            let unit_did = parent.get(&sub_did).copied().unwrap_or(0);
            parent.get(&unit_did).copied().unwrap_or(0)
        });
        if let Some(root_did) = root.filter(|&d| d != 0) {
            let cc = sum_subtopic_counts(cross_tags.iter().map(String::as_str), tag_deck, counts);
            if is_actionable(cc) {
                items.push(PlanItem {
                    tier: StudyMode::CrossUnit,
                    deck_id: root_did,
                    subtopic_tag: None,
                    unit_id: None,
                    new: cc.0,
                    review: cc.1,
                    learn: cc.2,
                    total: cc.3,
                });
            }
        }
    }

    items
}

/// Minimum study history (in days) before we extrapolate a mastery finish date.
/// Below this we have too little history to project a rate honestly, so the pace
/// reports the raw counts but abstains from a projection / on-track verdict —
/// the same give-up discipline the scores use, applied to the pace.
pub(crate) const MIN_PACE_HISTORY_DAYS: i64 = 7;

/// Mastery-pace arithmetic: given the subtopics still to master, how many are
/// already mastered, how long the student has been studying, and days until the
/// exam, work out the observed rate and whether it lands in time.
#[derive(Debug, Clone, Copy, PartialEq)]
pub(crate) struct MasteryPace {
    /// Observed average mastery rate so far (subtopics/week); 0 when unknown.
    pub current_per_week: f64,
    /// Rate needed to master the rest before the exam (subtopics/week); 0 with
    /// no future exam date or nothing remaining.
    pub recommended_per_week: f64,
    /// Projected days to master all remaining at the current rate; 0 when the
    /// rate is unknown.
    pub projected_days_to_finish: u32,
    pub on_track: bool,
}

/// Pure mastery-pace maths (no I/O), so it can be unit-tested. Everything is a
/// plain function of MEASURED counts + the user's date; it is a *mastery* pace
/// (subtopics clearing their gate), never a predicted exam score. With nothing
/// left to master the user is trivially "on track". The observed rate is the
/// average over the whole study history (mastered / weeks studied); we only
/// extrapolate it once something is mastered AND there is at least
/// MIN_PACE_HISTORY_DAYS of history, so a single fast day can't fake a pace.
/// `recommended` is remaining / weeks_left; `on_track` needs an exam date, a
/// known rate, and days remaining, with the projection landing on/before the
/// exam.
pub(crate) fn compute_mastery_pace(
    remaining: u32,
    mastered: u32,
    days_studied: i64,
    days_left: i64,
    has_exam_date: bool,
) -> MasteryPace {
    let recommended_per_week = if has_exam_date && days_left > 0 && remaining > 0 {
        remaining as f64 / (days_left as f64 / 7.0)
    } else {
        0.0
    };
    if remaining == 0 {
        // Whole syllabus mastered -> trivially on track, nothing to project.
        return MasteryPace {
            current_per_week: 0.0,
            recommended_per_week: 0.0,
            projected_days_to_finish: 0,
            on_track: true,
        };
    }
    // Only project once something is mastered AND there is enough history; below
    // that the average rate is undefined / too noisy to extrapolate honestly.
    let can_project = mastered > 0 && days_studied >= MIN_PACE_HISTORY_DAYS;
    let current_per_week = if can_project {
        mastered as f64 / (days_studied as f64 / 7.0)
    } else {
        0.0
    };
    let projected_days_to_finish = if can_project {
        (remaining as f64 * days_studied as f64 / mastered as f64).ceil() as u32
    } else {
        0
    };
    let on_track = has_exam_date
        && can_project
        && days_left > 0
        && (projected_days_to_finish as i64) <= days_left;
    MasteryPace {
        current_per_week,
        recommended_per_week,
        projected_days_to_finish,
        on_track,
    }
}

/// Order new cards by tier: blocked subtopics first (grouped so each is
/// practiced in isolation), then within-unit interleaving (a unit's cleared
/// sub-types alternated together), then cross-unit interleaving. Cards whose
/// subtopic is unknown sort last, preserving their input order.
pub(crate) fn order_new_cards(
    cards: &[(CardId, String)],
    pools: &HashMap<String, Pool>,
    ablate_within_unit: bool,
) -> Vec<CardId> {
    // Tier rank. Full (build 1): Blocked -> within-unit -> cross-unit. Ablated
    // (build 2): the within-unit tier is removed, so every cleared subtopic
    // collapses into a single mixed pool (rank 1). Unknown subtopics sort last.
    let rank = |pool: Option<Pool>| -> u8 {
        match pool {
            Some(Pool::Blocked) => 0,
            Some(Pool::WithinUnit) => 1,
            Some(Pool::CrossUnit) => {
                if ablate_within_unit {
                    1
                } else {
                    2
                }
            }
            None => 3,
        }
    };
    // Round-robin position of each card within its OWN subtopic, in input order
    // (0 for the first card of that subtopic, 1 for the second, ...). The Full
    // within-unit tier sorts by this first, so a unit's cleared sub-types are
    // genuinely alternated (x1, y1, x2, y2, ...) instead of being concatenated
    // by whatever order they were gathered in — this is the actual within-unit
    // *interleaving*, robust to gather order.
    let mut seen_per_tag: HashMap<&str, usize> = HashMap::new();
    let rr_index: Vec<usize> = cards
        .iter()
        .map(|(_, tag)| {
            let n = seen_per_tag.entry(tag.as_str()).or_insert(0);
            let idx = *n;
            *n += 1;
            idx
        })
        .collect();
    // Sort key within a tier `(group, round_robin, subtopic)`:
    // - Blocked: group by subtopic (round-robin/subtopic unused) -> each
    //   subtopic drilled together in isolation.
    // - Full within-unit: group by UNIT, then round-robin across the unit's
    //   cleared sub-types (this IS the within-unit interleaving the ablation
    //   removes — confusable siblings mixed *with each other*).
    // - Ablated mixed pool + cross-unit spacing: no grouping, so cleared cards
    //   interleave globally in input order.
    let key = |r: u8, pool: Option<Pool>, tag: &str, rr: usize| -> (String, usize, String) {
        if r == 0 {
            (tag.to_string(), 0, String::new())
        } else if !ablate_within_unit && matches!(pool, Some(Pool::WithinUnit)) {
            let unit = parse_subtopic_tag(tag).map(|(u, _)| u).unwrap_or_default();
            (unit, rr, tag.to_string())
        } else {
            (String::new(), 0, String::new())
        }
    };
    let mut keyed: Vec<(u8, (String, usize, String), usize, CardId)> = cards
        .iter()
        .enumerate()
        .map(|(i, (cid, tag))| {
            let pool = pools.get(tag).copied();
            let r = rank(pool);
            (r, key(r, pool, tag, rr_index[i]), i, *cid)
        })
        .collect();
    keyed.sort_by(|a, b| {
        a.0.cmp(&b.0)
            .then_with(|| a.1.cmp(&b.1))
            .then_with(|| a.2.cmp(&b.2))
    });
    keyed.into_iter().map(|(_, _, _, cid)| cid).collect()
}

/// The card ids to KEEP when a study session is scoped to `tier` — the strict
/// tier rule applied to a gathered queue. A card is kept when its subtopic is in
/// an eligible pool for the tier (`pool_eligible_for_tier`); a card carrying NO
/// syllabus subtopic (`tag == None`) is always kept, so only the tiered syllabus
/// is scoped and any non-speedrun card sharing the deck is never dropped. A
/// syllabus card whose subtopic isn't in `pools` (shouldn't happen — pools are
/// computed over every present subtopic) is dropped, matching "serve ONLY the
/// subtopics in this tier". Pure and order-preserving, so the strict-tier
/// behaviour is unit-testable without a live collection.
pub(crate) fn scope_cards_to_tier(
    cards: &[(CardId, Option<String>)],
    pools: &HashMap<String, Pool>,
    tier: TierScope,
) -> Vec<CardId> {
    cards
        .iter()
        .filter(|(_, tag)| match tag {
            Some(t) => pools
                .get(t)
                .map(|p| pool_eligible_for_tier(*p, tier))
                .unwrap_or(false),
            None => true,
        })
        .map(|(cid, _)| *cid)
        .collect()
}

/// Measured weakness of a subtopic in [0, 1]: `1 - mean FSRS retrievability`.
/// With no retention evidence yet we return a neutral 0.5 rather than guess, so
/// weakness is always grounded in real reviews.
pub(crate) fn subtopic_weakness(s: &SubtopicStats) -> f64 {
    if s.retr_count == 0 {
        0.5
    } else {
        (1.0 - s.mean_retrievability()).clamp(0.0, 1.0)
    }
}

/// A due card scored by "points at stake" = topic importance weight x student
/// weakness on that topic.
#[derive(Debug, Clone, PartialEq)]
pub(crate) struct StakeCard {
    pub card_id: CardId,
    pub tag: String,
    pub weight: f64,
    pub weakness: f64,
    pub stakes: f64,
    pub retrievability: f64,
}

/// Order due cards by points at stake, highest first. `cards` is
/// `(card id, subtopic tag, per-card retrievability)`. `weights` maps a
/// subtopic tag to its importance weight; when it is empty every subtopic is
/// treated as equally weighted, so the order reduces to weakest-topic-first.
/// `weakness` maps a subtopic tag to its measured weakness in [0, 1]. Ties in
/// stakes are broken by the more-urgent card (lower retrievability), then by
/// the input order, so the result is deterministic. Pure ordering — it never
/// reschedules a card, so FSRS intervals stay valid.
pub(crate) fn points_at_stake_order(
    cards: &[(CardId, String, f64)],
    weights: &HashMap<String, f64>,
    weakness: &HashMap<String, f64>,
) -> Vec<StakeCard> {
    let use_equal = weights.is_empty();
    let mut out: Vec<StakeCard> = cards
        .iter()
        .map(|(id, tag, retr)| {
            let weight = if use_equal {
                1.0
            } else {
                weights.get(tag).copied().unwrap_or(0.0)
            };
            let wk = weakness.get(tag).copied().unwrap_or(0.5);
            StakeCard {
                card_id: *id,
                tag: tag.clone(),
                weight,
                weakness: wk,
                stakes: weight * wk,
                retrievability: *retr,
            }
        })
        .collect();
    out.sort_by(|a, b| {
        b.stakes
            .partial_cmp(&a.stakes)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then(
                a.retrievability
                    .partial_cmp(&b.retrievability)
                    .unwrap_or(std::cmp::Ordering::Equal),
            )
    });
    out
}

impl Collection {
    /// Accumulate per-subtopic review stats for the expected subtopic tags,
    /// reading real revlog accuracy and FSRS retrievability from the
    /// collection.
    pub(crate) fn speedrun_subtopic_stats(
        &mut self,
        expected_subtopics: &[String],
    ) -> Result<Vec<SubtopicStats>> {
        // Seed the result in the caller's order so output is deterministic.
        let mut order: Vec<String> = Vec::new();
        let mut map: HashMap<String, SubtopicStats> = HashMap::new();
        for tag in expected_subtopics {
            if let Some((unit, sub)) = parse_subtopic_tag(tag) {
                if !map.contains_key(tag) {
                    order.push(tag.clone());
                    map.insert(tag.clone(), SubtopicStats::new(&unit, &sub));
                }
            }
        }
        if map.is_empty() {
            return Ok(Vec::new());
        }

        let timing = self.timing_today()?;
        let today = timing.days_elapsed as i64;
        let next_day_at = timing.next_day_at.0;
        let now = TimestampSecs::now().0;

        // Drive from an aggregated revlog so the scan scales with the number of
        // *reviewed* cards, not the whole collection: a never-reviewed card has
        // no graded rows (so it adds 0 reviews) and no FSRS memory state (so its
        // retrievability is NULL), i.e. it can never change a subtopic's gate.
        // Skipping those cards keeps the mastery query fast on a 50k-card deck.
        let sql = "
            SELECT n.tags,
                   extract_fsrs_retrievability(
                       c.data,
                       case when c.odue != 0 then c.odue else c.due end,
                       c.ivl, ?1, ?2, ?3),
                   r.reviews,
                   r.passes
            FROM (SELECT cid,
                         count(*) AS reviews,
                         sum(case when ease >= 2 then 1 else 0 end) AS passes
                  FROM revlog
                  WHERE ease >= 1
                  GROUP BY cid) r
            JOIN cards c ON c.id = r.cid
            JOIN notes n ON n.id = c.nid
            WHERE n.tags LIKE '% subtopic::%'";

        let mut stmt = self.storage.db.prepare_cached(sql)?;
        let mut rows = stmt.query([today, next_day_at, now])?;
        while let Some(row) = rows.next()? {
            let tags: String = row.get(0)?;
            let retr: Option<f64> = row.get(1)?;
            let reviews: i64 = row.get(2)?;
            let passes: i64 = row.get(3)?;
            for tag in tags.split_whitespace() {
                if let Some(stat) = map.get_mut(tag) {
                    stat.reviews += reviews.max(0) as u32;
                    stat.correct += passes.max(0) as u32;
                    if let Some(r) = retr {
                        stat.retr_sum += r;
                        stat.retr_count += 1;
                        stat.retr_values.push(r);
                    }
                }
            }
        }

        Ok(order.into_iter().map(|t| map.remove(&t).unwrap()).collect())
    }

    /// New (unstudied) cards in the collection paired with their subtopic tag,
    /// for mastery-ordered presentation. Cards with no subtopic tag are
    /// omitted.
    pub(crate) fn speedrun_new_cards_with_subtopic(
        &mut self,
        expected_subtopics: &[String],
    ) -> Result<Vec<(CardId, String)>> {
        use std::collections::HashSet;
        let expected: HashSet<&str> = expected_subtopics.iter().map(String::as_str).collect();
        let sql = "
            SELECT c.id, n.tags
            FROM cards c JOIN notes n ON c.nid = n.id
            WHERE c.queue = 0 AND n.tags LIKE '% subtopic::%'
            ORDER BY c.due, c.id";
        let mut stmt = self.storage.db.prepare_cached(sql)?;
        let mut rows = stmt.query([])?;
        let mut out = Vec::new();
        while let Some(row) = rows.next()? {
            let cid: i64 = row.get(0)?;
            let tags: String = row.get(1)?;
            if let Some(tag) = tags.split_whitespace().find(|t| expected.contains(*t)) {
                out.push((CardId(cid), tag.to_string()));
            }
        }
        Ok(out)
    }

    /// Due cards in the review pipeline (learning, review, interday learning)
    /// that carry a syllabus subtopic tag, paired with the subtopic and the
    /// card's FSRS retrievability, for points-at-stake ordering. Read-only.
    pub(crate) fn speedrun_due_cards_with_subtopic(
        &mut self,
        expected_subtopics: &[String],
    ) -> Result<Vec<(CardId, String, f64)>> {
        use std::collections::HashSet;
        let expected: HashSet<&str> = expected_subtopics.iter().map(String::as_str).collect();
        let timing = self.timing_today()?;
        let today = timing.days_elapsed as i64;
        let next_day_at = timing.next_day_at.0;
        let now = TimestampSecs::now().0;
        let sql = "
            SELECT c.id, n.tags,
                   extract_fsrs_retrievability(
                       c.data,
                       case when c.odue != 0 then c.odue else c.due end,
                       c.ivl, ?1, ?2, ?3)
            FROM cards c JOIN notes n ON c.nid = n.id
            WHERE c.queue IN (1, 2, 3) AND n.tags LIKE '% subtopic::%'";
        let mut stmt = self.storage.db.prepare_cached(sql)?;
        let mut rows = stmt.query([today, next_day_at, now])?;
        let mut out = Vec::new();
        while let Some(row) = rows.next()? {
            let cid: i64 = row.get(0)?;
            let tags: String = row.get(1)?;
            let retr: Option<f64> = row.get(2)?;
            if let Some(tag) = tags.split_whitespace().find(|t| expected.contains(*t)) {
                out.push((CardId(cid), tag.to_string(), retr.unwrap_or(0.0)));
            }
        }
        Ok(out)
    }

    /// Map each syllabus subtopic tag to the deck its cards live in. Used by
    /// the tiered study plan to look up a subtopic deck's real due counts.
    /// When a subtopic's cards are split across decks (unusual), the deck
    /// holding the most of them wins, so the plan points at the deck that
    /// actually has the cards. Read-only.
    pub(crate) fn speedrun_subtopic_deck_ids(
        &mut self,
        expected_subtopics: &[String],
    ) -> Result<HashMap<String, i64>> {
        use std::collections::HashSet;
        let expected: HashSet<&str> = expected_subtopics.iter().map(String::as_str).collect();
        // Attribute each card to its HOME deck: a card pulled into a filtered
        // ("cram") deck has `did` = the filtered deck and `odid` = its real deck,
        // so use `odid` when set. Without this, cramming (e.g. "Review everything")
        // makes every subtopic resolve to the one filtered deck, and the study
        // plan shows that deck's whole count for each subtopic.
        let sql = "
            SELECT (CASE WHEN c.odid != 0 THEN c.odid ELSE c.did END), n.tags
            FROM cards c JOIN notes n ON c.nid = n.id
            WHERE n.tags LIKE '% subtopic::%'";
        let mut stmt = self.storage.db.prepare_cached(sql)?;
        let mut rows = stmt.query([])?;
        // (tag, deck id) -> number of cards, so we can pick the dominant deck.
        let mut tally: HashMap<(String, i64), u32> = HashMap::new();
        while let Some(row) = rows.next()? {
            let did: i64 = row.get(0)?;
            let tags: String = row.get(1)?;
            if let Some(tag) = tags.split_whitespace().find(|t| expected.contains(*t)) {
                *tally.entry((tag.to_string(), did)).or_default() += 1;
            }
        }
        let mut best: HashMap<String, (i64, u32)> = HashMap::new();
        for ((tag, did), n) in tally {
            let entry = best.entry(tag).or_insert((did, 0));
            if n > entry.1 {
                *entry = (did, n);
            }
        }
        Ok(best.into_iter().map(|(tag, (did, _))| (tag, did)).collect())
    }

    /// Whether the opt-in three-tier mastery scheduler is enabled. Reads a
    /// plain string config key so upstream's `BoolKey` enum is untouched;
    /// defaults to false so the live queue is unchanged unless a user
    /// explicitly turns it on.
    pub(crate) fn speedrun_mastery_scheduler_enabled(&self) -> bool {
        self.get_config_optional::<bool, _>(MASTERY_SCHEDULER_KEY)
            .unwrap_or(false)
    }

    /// Study-feature ablation switch (brief 8, build 2). When on, the
    /// within-unit interleaving tier is removed from the new-card order.
    /// Default false (build 1 = full three-tier scheduler). Only has an
    /// effect when the mastery scheduler is also on.
    pub(crate) fn speedrun_ablate_within_unit(&self) -> bool {
        self.get_config_optional::<bool, _>(ABLATE_WITHIN_UNIT_KEY)
            .unwrap_or(false)
    }

    /// Whether guided-learning mode (the hard prerequisite gate) is on.
    /// Defaults TRUE: a fresh learner is guided through the curriculum
    /// order. Turning it off ("free mode") is the experienced-user bypass.
    pub(crate) fn speedrun_guided_mode_enabled(&self) -> bool {
        self.get_config_optional::<bool, _>(GUIDED_MODE_KEY)
            .unwrap_or(true)
    }

    /// Subtopic tags the user has explicitly unlocked (per-topic gate bypass).
    /// Empty by default.
    pub(crate) fn speedrun_unlocked_subtopics_config(&self) -> std::collections::HashSet<String> {
        self.get_config_optional::<Vec<String>, _>(UNLOCKED_SUBTOPICS_KEY)
            .unwrap_or_default()
            .into_iter()
            .collect()
    }

    /// Per-subtopic practice-test performance from config (tag -> Performance).
    /// Empty when no test has been graded. A separate signal from the memory
    /// gate; used to satisfy prerequisites and to report the Performance row.
    pub(crate) fn speedrun_performance_config(&self) -> HashMap<String, Performance> {
        #[derive(serde::Deserialize)]
        struct Cell {
            #[serde(default)]
            questions: u32,
            #[serde(default)]
            correct: u32,
        }
        self.get_config_optional::<HashMap<String, Cell>, _>(PERFORMANCE_KEY)
            .unwrap_or_default()
            .into_iter()
            .map(|(tag, c)| {
                (
                    tag,
                    Performance {
                        questions: c.questions,
                        correct: c.correct,
                    },
                )
            })
            .collect()
    }

    /// The guided-learning DAG from config: subtopic edges (tag -> prereq
    /// tags). Empty when unset, which makes the gate a no-op.
    pub(crate) fn speedrun_subtopic_prereqs_config(&self) -> HashMap<String, Vec<String>> {
        self.get_config_optional::<HashMap<String, Vec<String>>, _>(SUBTOPIC_PREREQS_KEY)
            .unwrap_or_default()
    }

    /// The guided-learning DAG from config: unit edges (unit -> prereq units).
    pub(crate) fn speedrun_unit_prereqs_config(&self) -> HashMap<String, Vec<String>> {
        self.get_config_optional::<HashMap<String, Vec<String>>, _>(UNIT_PREREQS_KEY)
            .unwrap_or_default()
    }

    /// Map each note that carries a `subtopic::` tag to its first such tag.
    /// Used to attach a subtopic to each gathered new card for tier
    /// ordering.
    fn speedrun_note_subtopic_map(&mut self) -> Result<HashMap<NoteId, String>> {
        let sql = "SELECT id, tags FROM notes WHERE tags LIKE '% subtopic::%'";
        let mut stmt = self.storage.db.prepare_cached(sql)?;
        let mut rows = stmt.query([])?;
        let mut out = HashMap::new();
        while let Some(row) = rows.next()? {
            let nid: i64 = row.get(0)?;
            let tags: String = row.get(1)?;
            if let Some(tag) = tags
                .split_whitespace()
                .find(|t| t.starts_with("subtopic::"))
            {
                out.insert(NoteId(nid), tag.to_string());
            }
        }
        Ok(out)
    }

    /// Reorder already-gathered new cards by mastery tier: Blocked (practice a
    /// subtopic in isolation) -> WithinUnit (interleave confusable sub-types)
    /// -> CrossUnit (spacing). Blocked subtopics are grouped so each is
    /// practiced together. Cards without a subtopic tag keep their relative
    /// order at the end, so non-syllabus decks are unaffected. Read-only
    /// (no writes, so undo and integrity are untouched); only called when
    /// the flag is on.
    pub(crate) fn speedrun_reorder_new_cards(&mut self, new: &mut Vec<NewCard>) -> Result<()> {
        if new.len() < 2 {
            return Ok(());
        }
        let note_subtopics = self.speedrun_note_subtopic_map()?;
        // If no gathered new card is a syllabus card, leave the queue untouched.
        if !new.iter().any(|c| note_subtopics.contains_key(&c.note_id)) {
            return Ok(());
        }
        // Pools depend on whole-unit mastery, so compute stats over every
        // syllabus subtopic present in the collection, not just the new cards'.
        let mut seen = std::collections::HashSet::new();
        let all_subtopics: Vec<String> = note_subtopics
            .values()
            .filter(|t| seen.insert((*t).clone()))
            .cloned()
            .collect();
        let stats = self.speedrun_subtopic_stats(&all_subtopics)?;
        let pools = compute_pools(&stats);
        let ablate = self.speedrun_ablate_within_unit();

        let empty = String::new();
        let cards: Vec<(CardId, String)> = new
            .iter()
            .map(|c| {
                (
                    c.id,
                    note_subtopics.get(&c.note_id).unwrap_or(&empty).clone(),
                )
            })
            .collect();
        let ordered = order_new_cards(&cards, &pools, ablate);

        let mut by_id: HashMap<CardId, NewCard> = new.iter().map(|c| (c.id, *c)).collect();
        let reordered: Vec<NewCard> = ordered
            .into_iter()
            .filter_map(|id| by_id.remove(&id))
            .collect();
        // Only apply if it's a clean permutation (never drop or dupe a card).
        if reordered.len() == new.len() {
            *new = reordered;
        }
        Ok(())
    }

    /// The hard guided gate: when guided mode is on, withhold NEW cards for
    /// subtopics whose prerequisites aren't satisfied yet (memory gate cleared
    /// OR performance mastered), unless the subtopic is explicitly unlocked. A
    /// read-only queue filter — like a per-deck new-card limit — so it writes
    /// nothing; undo, FSRS intervals, and collection integrity are untouched.
    /// Deliberately a no-op when no DAG is configured (upstream tests / plain
    /// decks) or when no gathered new card is a syllabus card. Reviews and
    /// practice tests are never gated.
    pub(crate) fn speedrun_gate_new_cards(&mut self, new: &mut Vec<NewCard>) -> Result<()> {
        use std::collections::HashSet;
        if new.is_empty() {
            return Ok(());
        }
        let subtopic_prereqs = self.speedrun_subtopic_prereqs_config();
        let unit_prereqs = self.speedrun_unit_prereqs_config();
        if subtopic_prereqs.is_empty() && unit_prereqs.is_empty() {
            return Ok(());
        }
        let note_subtopics = self.speedrun_note_subtopic_map()?;
        if !new.iter().any(|c| note_subtopics.contains_key(&c.note_id)) {
            return Ok(());
        }
        // Locks depend on whole-unit satisfaction, so compute over every
        // syllabus subtopic present, not just the gathered new cards'.
        let mut seen = HashSet::new();
        let all_subtopics: Vec<String> = note_subtopics
            .values()
            .filter(|t| seen.insert((*t).clone()))
            .cloned()
            .collect();
        let stats = self.speedrun_subtopic_stats(&all_subtopics)?;
        let perf = self.speedrun_performance_config();
        let unlocked = self.speedrun_unlocked_subtopics_config();
        let locks = compute_locks(
            &stats,
            &perf,
            &subtopic_prereqs,
            &unit_prereqs,
            &unlocked,
            true,
        );
        let locked: HashSet<&str> = locks
            .iter()
            .filter(|(_, v)| v.locked)
            .map(|(k, _)| k.as_str())
            .collect();
        if locked.is_empty() {
            return Ok(());
        }
        let empty = String::new();
        new.retain(|c| {
            let tag = note_subtopics.get(&c.note_id).unwrap_or(&empty);
            !locked.contains(tag.as_str())
        });
        Ok(())
    }

    /// Whether the opt-in points-at-stake live review order is enabled. Default
    /// false, so the review queue is unchanged unless a user turns it on.
    pub(crate) fn speedrun_points_at_stake_enabled(&self) -> bool {
        self.get_config_optional::<bool, _>(POINTS_AT_STAKE_KEY)
            .unwrap_or(false)
    }

    /// Per-subtopic importance weights from config (written by Python from the
    /// topic map). Empty when unset, which makes the reorder weight every
    /// subtopic equally (weakest-topic-first).
    fn speedrun_subtopic_weights_config(&self) -> HashMap<String, f64> {
        self.get_config_optional::<HashMap<String, f64>, _>(SUBTOPIC_WEIGHTS_KEY)
            .unwrap_or_default()
    }

    /// Reorder already-gathered due review cards by points at stake (topic
    /// importance weight x measured student weakness), highest-value first, so
    /// weak-topic cards come back sooner. Only invoked when the flag is on.
    /// Read-only: it reorders presentation only and never reschedules, so FSRS
    /// intervals stay valid and undo/integrity are untouched. Cards without a
    /// syllabus subtopic keep their relative order.
    pub(crate) fn speedrun_reorder_review_cards(
        &mut self,
        review: &mut Vec<DueCard>,
    ) -> Result<()> {
        if review.len() < 2 {
            return Ok(());
        }
        let note_subtopics = self.speedrun_note_subtopic_map()?;
        if !review
            .iter()
            .any(|c| note_subtopics.contains_key(&c.note_id))
        {
            return Ok(());
        }
        let mut seen = std::collections::HashSet::new();
        let all_subtopics: Vec<String> = note_subtopics
            .values()
            .filter(|t| seen.insert((*t).clone()))
            .cloned()
            .collect();
        let stats = self.speedrun_subtopic_stats(&all_subtopics)?;
        let weakness: HashMap<String, f64> = stats
            .iter()
            .map(|s| (s.tag(), subtopic_weakness(s)))
            .collect();
        let weights = self.speedrun_subtopic_weights_config();

        let empty = String::new();
        let cards: Vec<(CardId, String, f64)> = review
            .iter()
            .map(|c| {
                (
                    c.id,
                    note_subtopics.get(&c.note_id).unwrap_or(&empty).clone(),
                    0.0,
                )
            })
            .collect();
        let ordered = points_at_stake_order(&cards, &weights, &weakness);

        let mut by_id: HashMap<CardId, DueCard> = review.iter().map(|c| (c.id, *c)).collect();
        let reordered: Vec<DueCard> = ordered
            .into_iter()
            .filter_map(|s| by_id.remove(&s.card_id))
            .collect();
        if reordered.len() == review.len() {
            *review = reordered;
        }
        Ok(())
    }

    /// Reorder already-gathered due review cards by mastery tier, so blocked
    /// practice carries through the REVIEW queue until a subtopic clears its
    /// gate: a not-yet-mastered subtopic's due cards are grouped and served
    /// first (blocked drill), then within-unit interleaving, then cross-unit.
    /// Reuses the exact new-card tier order (`order_new_cards`) and honours the
    /// same within-unit ablation flag. Only invoked when the mastery scheduler
    /// flag is on. Read-only: a stable reorder that never reschedules, so FSRS
    /// intervals and undo/integrity are untouched. Applied after the
    /// points-at-stake reorder, so the tier is primary and stakes only break
    /// ties within a tier. Cards without a syllabus subtopic keep their
    /// relative order at the end.
    pub(crate) fn speedrun_reorder_review_cards_by_tier(
        &mut self,
        review: &mut Vec<DueCard>,
    ) -> Result<()> {
        if review.len() < 2 {
            return Ok(());
        }
        let note_subtopics = self.speedrun_note_subtopic_map()?;
        if !review
            .iter()
            .any(|c| note_subtopics.contains_key(&c.note_id))
        {
            return Ok(());
        }
        // Pools depend on whole-unit mastery, so compute stats over every
        // syllabus subtopic present, not just the ones due right now.
        let mut seen = std::collections::HashSet::new();
        let all_subtopics: Vec<String> = note_subtopics
            .values()
            .filter(|t| seen.insert((*t).clone()))
            .cloned()
            .collect();
        let stats = self.speedrun_subtopic_stats(&all_subtopics)?;
        let pools = compute_pools(&stats);
        let ablate = self.speedrun_ablate_within_unit();

        let empty = String::new();
        let cards: Vec<(CardId, String)> = review
            .iter()
            .map(|c| {
                (
                    c.id,
                    note_subtopics.get(&c.note_id).unwrap_or(&empty).clone(),
                )
            })
            .collect();
        let ordered = order_new_cards(&cards, &pools, ablate);

        let mut by_id: HashMap<CardId, DueCard> = review.iter().map(|c| (c.id, *c)).collect();
        let reordered: Vec<DueCard> = ordered
            .into_iter()
            .filter_map(|id| by_id.remove(&id))
            .collect();
        if reordered.len() == review.len() {
            *review = reordered;
        }
        Ok(())
    }

    /// The active tier scope for `deck_id`, if the transient
    /// `speedrunActiveTierScope` config is set AND keyed to this exact deck.
    /// Returns `None` when unset, malformed, targeting a different deck, or
    /// carrying an unknown tier — so a stale scope can never affect the wrong
    /// deck, and a missing/invalid value is simply a no-op (upstream/plain decks
    /// untouched). Read-only.
    pub(crate) fn speedrun_active_tier_scope(&self, deck_id: DeckId) -> Option<TierScope> {
        #[derive(serde::Deserialize)]
        struct ScopeConfig {
            #[serde(default)]
            deck_id: i64,
            #[serde(default)]
            tier: String,
        }
        let cfg: ScopeConfig = self.get_config_optional(ACTIVE_TIER_SCOPE_KEY)?;
        if cfg.deck_id != deck_id.0 {
            return None;
        }
        TierScope::from_config_str(&cfg.tier)
    }

    /// Strict tier study: when `deck_id` is the deck the active tier scope was
    /// set for, retain in the gathered `new` and `review` queues ONLY the cards
    /// whose subtopic is actually in that tier's mastery pool (within-unit study
    /// serves only WithinUnit-pool subtopics; cross-unit study serves only
    /// CrossUnit-pool subtopics). This stops a parent (unit/root) deck from
    /// serving its still-Blocked descendants — the tiers no longer leak. Pools
    /// depend on whole-unit mastery, so stats are computed over every syllabus
    /// subtopic present, not just the gathered cards' (mirrors the reorders).
    ///
    /// A no-op when no scope targets this deck, or when no gathered card is a
    /// syllabus card. Read-only: it only drops gathered cards from the in-memory
    /// queue (like the guided new-card gate / a per-deck limit), so it writes
    /// nothing — undo, FSRS intervals, and collection integrity are untouched —
    /// and cards without a syllabus subtopic are never dropped.
    pub(crate) fn speedrun_scope_queues_to_tier(
        &mut self,
        deck_id: DeckId,
        new: &mut Vec<NewCard>,
        review: &mut Vec<DueCard>,
    ) -> Result<()> {
        let Some(tier) = self.speedrun_active_tier_scope(deck_id) else {
            return Ok(());
        };
        let note_subtopics = self.speedrun_note_subtopic_map()?;
        // Nothing tiered gathered -> leave the queue exactly as built.
        let touches_syllabus = new.iter().any(|c| note_subtopics.contains_key(&c.note_id))
            || review.iter().any(|c| note_subtopics.contains_key(&c.note_id));
        if !touches_syllabus {
            return Ok(());
        }
        // Pools depend on whole-unit mastery, so compute over every syllabus
        // subtopic present (not just the ones gathered right now).
        let mut seen = std::collections::HashSet::new();
        let all_subtopics: Vec<String> = note_subtopics
            .values()
            .filter(|t| seen.insert((*t).clone()))
            .cloned()
            .collect();
        let stats = self.speedrun_subtopic_stats(&all_subtopics)?;
        let pools = compute_pools(&stats);

        let new_tagged: Vec<(CardId, Option<String>)> = new
            .iter()
            .map(|c| (c.id, note_subtopics.get(&c.note_id).cloned()))
            .collect();
        let keep_new: std::collections::HashSet<CardId> =
            scope_cards_to_tier(&new_tagged, &pools, tier)
                .into_iter()
                .collect();
        new.retain(|c| keep_new.contains(&c.id));

        let review_tagged: Vec<(CardId, Option<String>)> = review
            .iter()
            .map(|c| (c.id, note_subtopics.get(&c.note_id).cloned()))
            .collect();
        let keep_review: std::collections::HashSet<CardId> =
            scope_cards_to_tier(&review_tagged, &pools, tier)
                .into_iter()
                .collect();
        review.retain(|c| keep_review.contains(&c.id));
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::prelude::*;
    use crate::scheduler::queue::DueCardKind;
    use crate::tests::NoteAdder;

    fn stat(unit: &str, sub: &str, reviews: u32, correct: u32, mean_r: f64) -> SubtopicStats {
        SubtopicStats {
            unit_id: unit.into(),
            subtopic_id: sub.into(),
            reviews,
            correct,
            retr_sum: mean_r * reviews.max(1) as f64,
            retr_count: reviews.max(1),
            // Flat values at the mean, so the mean matches and helpers don't panic;
            // tests that need a spread build retr_values explicitly.
            retr_values: vec![mean_r; reviews.max(1) as usize],
            weight: 0.0,
            // Default to performance-mastered so `fully_mastered()` tracks the
            // memory gate for tests that only exercise the memory rollup; the
            // combined-gate test sets performance explicitly.
            performance: Performance {
                questions: MIN_PERF_QUESTIONS,
                correct: MIN_PERF_QUESTIONS,
            },
        }
    }

    fn stat_w(
        unit: &str,
        sub: &str,
        reviews: u32,
        correct: u32,
        mean_r: f64,
        weight: f64,
    ) -> SubtopicStats {
        SubtopicStats {
            weight,
            ..stat(unit, sub, reviews, correct, mean_r)
        }
    }

    #[test]
    fn percentile_band_brackets_the_spread() {
        // A clean 0.0..=1.0 ramp: 10th/90th percentiles sit near the ends but
        // inside them, and single/empty inputs degrade gracefully.
        let vals: Vec<f64> = (0..=10).map(|i| i as f64 / 10.0).collect();
        let (lo, hi) = percentile_band(&vals);
        assert!(lo > 0.0 && lo < 0.2, "lo={lo}");
        assert!(hi > 0.8 && hi < 1.0, "hi={hi}");
        assert_eq!(percentile_band(&[]), (0.0, 0.0));
        assert_eq!(percentile_band(&[0.7]), (0.7, 0.7));
    }

    #[test]
    fn memory_recall_is_measured_with_a_band_and_abstains_when_empty() {
        // No reviewed cards anywhere -> abstain (has_data false), never a number.
        let empty = vec![stat("u", "a", 0, 0, 0.0)];
        let mr = memory_recall(&empty);
        // stat() with 0 reviews still seeds one flat value; force a truly empty case:
        let mut truly_empty = stat("u", "a", 0, 0, 0.0);
        truly_empty.retr_values.clear();
        let mr_empty = memory_recall(&[truly_empty]);
        assert!(!mr_empty.has_data);
        assert_eq!(mr_empty.reviewed_cards, 0);
        // With a real spread of per-card retrievabilities, the point is the mean
        // and low < point < high.
        let mut s = stat("u", "a", 0, 0, 0.0);
        s.retr_values = vec![0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99];
        let mr2 = memory_recall(&[s]);
        assert!(mr2.has_data);
        assert_eq!(mr2.reviewed_cards, 7);
        assert!(mr2.low < mr2.point && mr2.point < mr2.high);
        // `mr` (flat 0-review seed) is just used to prove the fn accepts it.
        let _ = mr;
    }

    #[test]
    fn recall_band_matches_the_subtopics_values() {
        let mut s = stat("u", "a", 0, 0, 0.0);
        s.retr_values = vec![0.4, 0.5, 0.6, 0.7, 0.8, 0.9];
        let (lo, hi) = s.recall_band();
        assert!((0.4..0.6).contains(&lo));
        assert!(hi > 0.8 && hi <= 0.9);
    }

    #[test]
    fn gate_condition_needs_all_three_thresholds() {
        // Enough reviews, accurate, well-retained -> cleared.
        assert!(stat("u", "a", 10, 9, 0.95).gate_cleared());
        // Too few problems.
        assert!(!stat("u", "a", 9, 9, 0.99).gate_cleared());
        // Accuracy below 80%.
        assert!(!stat("u", "a", 20, 15, 0.99).gate_cleared());
        // Retrievability below 90%.
        assert!(!stat("u", "a", 20, 20, 0.89).gate_cleared());
        // Exactly on the thresholds passes.
        assert!(stat("u", "a", 10, 8, 0.90).gate_cleared());
    }

    #[test]
    fn tier_transition_blocked_then_within_then_cross() {
        // Unit "gp" has three subtopics; "uv" has one (its only subtopic).

        // Phase 1: only gp::a cleared. A LONE cleared sub-type can't interleave
        // (nothing to mix against), so it stays Blocked — not mislabeled as
        // within-unit. uv is fully mastered (its one subtopic) -> CrossUnit.
        let stats = vec![
            stat("gp", "a", 12, 12, 0.95), // cleared, but the only one in gp
            stat("gp", "b", 3, 1, 0.50),   // not cleared
            stat("gp", "c", 0, 0, 0.0),    // not started
            stat("uv", "x", 15, 15, 0.99), // uv's only subtopic -> unit mastered
        ];
        let pools = compute_pools(&stats);
        assert_eq!(
            pools["subtopic::gp::a"],
            Pool::Blocked,
            "a lone cleared sub-type has nothing to interleave -> stays Blocked"
        );
        assert_eq!(pools["subtopic::gp::b"], Pool::Blocked);
        assert_eq!(pools["subtopic::gp::c"], Pool::Blocked);
        assert_eq!(pools["subtopic::uv::x"], Pool::CrossUnit);

        // Phase 2: gp::b clears too -> gp now has 2 cleared sub-types, so both
        // promote to WithinUnit (genuine interleaving); gp::c stays Blocked.
        let stats2 = vec![
            stat("gp", "a", 12, 12, 0.95),
            stat("gp", "b", 12, 11, 0.95),
            stat("gp", "c", 0, 0, 0.0),
            stat("uv", "x", 15, 15, 0.99),
        ];
        let pools2 = compute_pools(&stats2);
        assert_eq!(pools2["subtopic::gp::a"], Pool::WithinUnit);
        assert_eq!(pools2["subtopic::gp::b"], Pool::WithinUnit);
        assert_eq!(pools2["subtopic::gp::c"], Pool::Blocked);

        // Phase 3: gp::c clears -> gp fully mastered, so every gp sub-type
        // promotes to CrossUnit (spacing across units).
        let stats3 = vec![
            stat("gp", "a", 12, 12, 0.95),
            stat("gp", "b", 12, 11, 0.95),
            stat("gp", "c", 12, 12, 0.95),
            stat("uv", "x", 15, 15, 0.99),
        ];
        let pools3 = compute_pools(&stats3);
        assert_eq!(pools3["subtopic::gp::a"], Pool::CrossUnit);
        assert_eq!(pools3["subtopic::gp::b"], Pool::CrossUnit);
        assert_eq!(pools3["subtopic::gp::c"], Pool::CrossUnit);
    }

    #[test]
    fn lone_cleared_subtopic_stays_blocked_until_a_sibling_clears() {
        // Regression: a single cleared sub-type in a not-yet-mastered unit must
        // NOT be reported as within-unit interleaving (there is nothing to
        // interleave). It stays Blocked, and only becomes WithinUnit once a
        // second sub-type in the same unit clears. This keeps the review banner
        // consistent with the study plan / recommendation (both need >= 2).
        let one = vec![
            stat("uv", "continuous_dists", 12, 12, 0.95), // cleared, alone
            stat("uv", "discrete_dists", 4, 2, 0.60),     // not cleared
            stat("uv", "insurance_apps", 0, 0, 0.0),      // not started
        ];
        let pools_one = compute_pools(&one);
        assert_eq!(pools_one["subtopic::uv::continuous_dists"], Pool::Blocked);

        let two = vec![
            stat("uv", "continuous_dists", 12, 12, 0.95), // cleared
            stat("uv", "discrete_dists", 12, 12, 0.95),   // now cleared too
            stat("uv", "insurance_apps", 0, 0, 0.0),      // still not started
        ];
        let pools_two = compute_pools(&two);
        assert_eq!(
            pools_two["subtopic::uv::continuous_dists"],
            Pool::WithinUnit
        );
        assert_eq!(pools_two["subtopic::uv::discrete_dists"], Pool::WithinUnit);
        assert_eq!(pools_two["subtopic::uv::insurance_apps"], Pool::Blocked);
    }

    #[test]
    fn pool_ordering_blocked_first_then_within_then_cross() {
        // gp has 2 cleared (a, b -> WithinUnit) + 1 blocking (c); uv's only
        // subtopic is cleared -> uv mastered -> CrossUnit.
        let stats = vec![
            stat("gp", "a", 12, 12, 0.95), // WithinUnit (2 cleared in gp)
            stat("gp", "b", 12, 12, 0.95), // WithinUnit
            stat("gp", "c", 0, 0, 0.0),    // Blocked (blocks the unit)
            stat("uv", "x", 15, 15, 0.99), // CrossUnit
        ];
        let pools = compute_pools(&stats);
        assert_eq!(pools["subtopic::gp::a"], Pool::WithinUnit);
        let cards = vec![
            (CardId(1), "subtopic::uv::x".to_string()), // CrossUnit (rank 2)
            (CardId(2), "subtopic::gp::a".to_string()), // WithinUnit (rank 1)
            (CardId(3), "subtopic::gp::c".to_string()), // Blocked (rank 0)
            (CardId(4), "subtopic::unknown::z".to_string()), // unknown -> last
        ];
        let ordered = order_new_cards(&cards, &pools, false);
        assert_eq!(ordered, vec![CardId(3), CardId(2), CardId(1), CardId(4)]);
    }

    #[test]
    fn full_scheduler_groups_within_unit_cleared_cards_by_unit() {
        // Two units, each with 2 cleared (WithinUnit) subtypes + a blocking one.
        // The FULL build keeps each unit's within-unit cards together AND
        // alternates that unit's sub-types (genuine interleaving); the ABLATED
        // build drops the tier so all cleared cards mix globally by input order.
        let stats = vec![
            stat("gp", "a", 12, 12, 0.95), // cleared -> WithinUnit
            stat("gp", "b", 12, 12, 0.95), // cleared -> WithinUnit
            stat("gp", "c", 0, 0, 0.0),    // blocked (keeps gp unmastered)
            stat("uv", "x", 12, 12, 0.95), // cleared -> WithinUnit
            stat("uv", "y", 12, 12, 0.95), // cleared -> WithinUnit
            stat("uv", "z", 0, 0, 0.0),    // blocked (keeps uv unmastered)
        ];
        let pools = compute_pools(&stats);
        // Cards gathered with the two units INTERLEAVED in the input, so "keep a
        // unit's cards together" (Full) is visibly different from "global input
        // order" (Ablated).
        let cards = vec![
            (CardId(1), "subtopic::gp::a".to_string()),
            (CardId(2), "subtopic::uv::x".to_string()),
            (CardId(3), "subtopic::gp::b".to_string()),
            (CardId(4), "subtopic::uv::y".to_string()),
            (CardId(5), "subtopic::gp::a".to_string()),
            (CardId(6), "subtopic::uv::x".to_string()),
            (CardId(7), "subtopic::gp::b".to_string()),
            (CardId(8), "subtopic::uv::y".to_string()),
        ];
        // Full: gp's cards first (a1, b1, a2, b2 — its sub-types alternated),
        // then uv's cards (x1, y1, x2, y2). Each unit is contiguous AND its
        // sub-types are interleaved.
        assert_eq!(
            order_new_cards(&cards, &pools, false),
            vec![
                CardId(1),
                CardId(3),
                CardId(5),
                CardId(7),
                CardId(2),
                CardId(4),
                CardId(6),
                CardId(8)
            ]
        );
        // Ablated: within-unit tier removed -> one global mixed pool, so the
        // input order (units mixed) is preserved.
        assert_eq!(
            order_new_cards(&cards, &pools, true),
            vec![
                CardId(1),
                CardId(2),
                CardId(3),
                CardId(4),
                CardId(5),
                CardId(6),
                CardId(7),
                CardId(8)
            ]
        );
    }

    #[test]
    fn within_unit_tier_actually_interleaves_subtopics() {
        // The heart of the fix: even when a unit's cards are gathered
        // subtopic-BLOCKED (all of x, then all of y), the within-unit tier must
        // ALTERNATE the sub-types (x1, y1, x2, y2), so the tier genuinely draws
        // from ACROSS the unit's subtopics instead of being blocked practice
        // wearing an "interleaving" label.
        let stats = vec![
            stat("uv", "x", 12, 12, 0.95), // cleared -> WithinUnit
            stat("uv", "y", 12, 12, 0.95), // cleared -> WithinUnit
            stat("uv", "z", 0, 0, 0.0),    // blocked (keeps uv unmastered)
        ];
        let pools = compute_pools(&stats);
        // Worst case for interleaving: input is fully blocked by subtopic.
        let cards = vec![
            (CardId(1), "subtopic::uv::x".to_string()),
            (CardId(2), "subtopic::uv::x".to_string()),
            (CardId(3), "subtopic::uv::y".to_string()),
            (CardId(4), "subtopic::uv::y".to_string()),
        ];
        // Full round-robin: x1, y1, x2, y2 — adjacent cards are different
        // sub-types of the same unit.
        let full = order_new_cards(&cards, &pools, false);
        assert_eq!(full, vec![CardId(1), CardId(3), CardId(2), CardId(4)]);
        // Every adjacent pair is a genuine sub-type switch within the unit.
        let sub = |cid: CardId| cards.iter().find(|(c, _)| *c == cid).unwrap().1.clone();
        for pair in full.windows(2) {
            assert_ne!(sub(pair[0]), sub(pair[1]), "adjacent cards must alternate");
        }
    }

    #[test]
    fn ablated_collapses_within_and_cross_into_one_mixed_pool() {
        // gp::a is WithinUnit (gp has 2 cleared, a+c, but b blocks the unit);
        // uv::x is CrossUnit (uv fully mastered). Full serves the within-unit
        // card before the cross-unit card; ablated treats both cleared cards as
        // one mixed pool, so input order decides.
        let stats = vec![
            stat("gp", "a", 12, 12, 0.95), // cleared -> WithinUnit
            stat("gp", "c", 12, 12, 0.95), // cleared -> WithinUnit (2nd in gp)
            stat("gp", "b", 0, 0, 0.0),    // blocked (keeps gp unmastered)
            stat("uv", "x", 12, 12, 0.95), // uv's only subtopic -> CrossUnit
        ];
        let pools = compute_pools(&stats);
        assert_eq!(pools["subtopic::gp::a"], Pool::WithinUnit);
        assert_eq!(pools["subtopic::uv::x"], Pool::CrossUnit);
        let cards = vec![
            (CardId(1), "subtopic::uv::x".to_string()), // CrossUnit
            (CardId(2), "subtopic::gp::a".to_string()), // WithinUnit
        ];
        // Full: WithinUnit (rank 1) before CrossUnit (rank 2).
        assert_eq!(
            order_new_cards(&cards, &pools, false),
            vec![CardId(2), CardId(1)]
        );
        // Ablated: both cleared -> one mixed pool -> input order preserved.
        assert_eq!(
            order_new_cards(&cards, &pools, true),
            vec![CardId(1), CardId(2)]
        );
    }

    #[test]
    fn ablate_within_unit_flag_defaults_off_and_is_settable() {
        let mut col = Collection::new();
        assert!(!col.speedrun_ablate_within_unit());
        col.set_config_json(ABLATE_WITHIN_UNIT_KEY, &true, false)
            .unwrap();
        assert!(col.speedrun_ablate_within_unit());
    }

    #[test]
    fn overall_counts_partition_the_syllabus_and_are_measured() {
        // gp: one mastered, one untouched -> unit not mastered.
        // uv: its only subtopic mastered -> unit mastered.
        // mv: one in-progress (reviews but gate not cleared) -> unit not mastered.
        let stats = vec![
            stat("gp", "a", 12, 12, 0.95), // mastered
            stat("gp", "b", 0, 0, 0.0),    // not started
            stat("uv", "x", 15, 15, 0.99), // mastered (whole unit)
            stat("mv", "y", 4, 2, 0.60),   // in progress (too few + inaccurate)
        ];
        let o = mastery_overall(&stats);
        assert_eq!(o.subtopics_total, 4);
        assert_eq!(o.subtopics_mastered, 2);
        assert_eq!(o.subtopics_in_progress, 1);
        assert_eq!(o.subtopics_not_started, 1);
        // Partition invariant: the three buckets sum to the total.
        assert_eq!(
            o.subtopics_mastered + o.subtopics_in_progress + o.subtopics_not_started,
            o.subtopics_total
        );
        assert_eq!(o.units_total, 3);
        assert_eq!(o.units_mastered, 1); // only uv
        assert_eq!(o.total_reviews, 31); // 12 + 15 + 4; not-started adds 0
    }

    #[test]
    fn overall_on_empty_syllabus_is_all_zero() {
        let o = mastery_overall(&[]);
        assert_eq!(o, MasteryOverallCounts::default());
    }

    #[test]
    fn full_mastery_requires_both_memory_and_performance() {
        // A subtopic can clear the MEMORY gate (enough accurate, well-retained
        // reviews) yet still not be "mastered" until practice-test PERFORMANCE is
        // mastered too — the two gates are AND-ed, never averaged.
        let mut memory_only = stat("gp", "a", 12, 12, 0.95); // memory gate cleared
        memory_only.performance = Performance {
            questions: 2, // below the sample floor -> performance abstains
            correct: 2,
        };
        assert!(memory_only.gate_cleared());
        assert!(!memory_only.performance.mastered());
        assert!(!memory_only.fully_mastered());

        // With performance also mastered, it becomes fully mastered.
        let mut both = memory_only.clone();
        both.performance = Performance {
            questions: MIN_PERF_QUESTIONS,
            correct: MIN_PERF_QUESTIONS,
        };
        assert!(both.fully_mastered());

        // In the rollup: the memory-only subtopic is in-progress, not mastered.
        let o = mastery_overall(&[memory_only, both]);
        assert_eq!(o.subtopics_mastered, 1);
        assert_eq!(o.subtopics_in_progress, 1);
        assert_eq!(o.subtopics_not_started, 0);
    }

    #[test]
    fn weighted_mastery_uses_importance_weights() {
        // Unit "u": a heavy cleared subtopic (weight 9) + a light uncleared one
        // (weight 1). Weighted mastery = 9/10 = 0.9, not the 0.5 a plain count
        // would report — importance changes the picture honestly.
        let stats = vec![
            stat_w("u", "heavy", 12, 12, 0.95, 9.0), // cleared
            stat_w("u", "light", 4, 1, 0.50, 1.0),   // not cleared
        ];
        let w = weighted_mastery(&stats);
        assert!(
            (w.overall_pct - 0.9).abs() < 1e-9,
            "overall={}",
            w.overall_pct
        );
        assert!((w.per_unit_pct["u"] - 0.9).abs() < 1e-9);
        assert!((w.per_unit_weight["u"] - 10.0).abs() < 1e-9);
        assert!((w.overall_weight - 10.0).abs() < 1e-9);
    }

    #[test]
    fn weighted_mastery_falls_back_to_counts_without_weights() {
        // No weights supplied (all 0): weighted pct must equal the plain
        // cleared/total fraction, so callers that omit weights still get a
        // sensible number rather than a divide-by-zero.
        let stats = vec![
            stat("u", "a", 12, 12, 0.95), // cleared
            stat("u", "b", 0, 0, 0.0),    // not started
        ];
        let w = weighted_mastery(&stats);
        assert!(
            (w.overall_pct - 0.5).abs() < 1e-9,
            "overall={}",
            w.overall_pct
        );
        assert!((w.per_unit_pct["u"] - 0.5).abs() < 1e-9);
        assert_eq!(w.overall_weight, 0.0);
    }

    #[test]
    fn study_priorities_rank_by_weight_then_drop_cleared() {
        // Two not-started subtopics: the heavier one ranks first. A cleared one
        // is dropped entirely (no study priority left).
        let stats = vec![
            stat_w("u", "light", 0, 0, 0.0, 1.0),   // not started, weight 1
            stat_w("u", "heavy", 0, 0, 0.0, 9.0),   // not started, weight 9
            stat_w("u", "done", 12, 12, 0.95, 5.0), // cleared -> dropped
        ];
        let p = study_priorities(&stats);
        assert_eq!(p.len(), 2, "cleared subtopics are dropped");
        assert_eq!(p[0].subtopic_id, "heavy");
        assert_eq!(p[1].subtopic_id, "light");
        assert!(p[0].score > p[1].score);
    }

    #[test]
    fn study_priorities_prefer_not_started_at_equal_weight() {
        // Equal weight: a not-started subtopic (full opportunity) outranks one
        // already partway to its gate.
        let stats = vec![
            stat_w("u", "started", 20, 15, 0.85, 5.0), // in progress (acc 0.75)
            stat_w("u", "fresh", 0, 0, 0.0, 5.0),      // not started
        ];
        let p = study_priorities(&stats);
        assert_eq!(p[0].subtopic_id, "fresh");
        assert_eq!(p[1].subtopic_id, "started");
    }

    #[test]
    fn study_priorities_fall_back_to_equal_weight() {
        // No weights supplied: ranking still works, ordered by opportunity.
        let stats = vec![
            stat("u", "a", 0, 0, 0.0), // not started -> opportunity 1.0
            stat("u", "b", 5, 5, 1.0), // gathering -> opportunity 0.8
        ];
        let p = study_priorities(&stats);
        assert_eq!(p[0].subtopic_id, "a");
        assert_eq!(p[1].subtopic_id, "b");
        assert!(p[0].score > 0.0);
    }

    #[test]
    fn recommend_blocked_when_nothing_cleared() {
        let stats = vec![
            stat_w("gp", "a", 0, 0, 0.0, 3.0),
            stat_w("gp", "b", 5, 2, 0.5, 5.0),
        ];
        let r = recommend_study(&stats);
        assert_eq!(r.mode, StudyMode::Blocked);
        assert!(r.subtopic_tag.is_some());
    }

    #[test]
    fn recommend_within_unit_when_a_unit_has_two_cleared() {
        // gp has 2 cleared + 1 uncleared -> interleave gp; uv is untouched.
        let stats = vec![
            stat("gp", "a", 12, 12, 0.95),
            stat("gp", "b", 12, 12, 0.95),
            stat("gp", "c", 0, 0, 0.0),
            stat("uv", "x", 0, 0, 0.0),
        ];
        let r = recommend_study(&stats);
        assert_eq!(r.mode, StudyMode::WithinUnit);
        assert_eq!(r.unit_id.as_deref(), Some("gp"));
    }

    #[test]
    fn recommend_cross_unit_when_all_cleared() {
        let stats = vec![stat("gp", "a", 12, 12, 0.95), stat("uv", "x", 12, 12, 0.95)];
        assert_eq!(recommend_study(&stats).mode, StudyMode::CrossUnit);
    }

    // --- tiered "today" study plan (pure tiering + actionable filter) ---

    #[test]
    fn study_plan_groups_decks_by_tier() {
        // gp: a,b cleared + c blocked -> gp within-unit (2 cleared, not mastered).
        // uv: its only subtopic cleared -> uv mastered -> cross-unit unlocks.
        let stats = vec![
            stat("gp", "a", 12, 12, 0.95),
            stat("gp", "b", 12, 12, 0.95),
            stat("gp", "c", 0, 0, 0.0),
            stat("uv", "x", 12, 12, 0.95),
        ];
        let pools = compute_pools(&stats);
        let tag_deck = HashMap::from([
            ("subtopic::gp::a".to_string(), 101i64),
            ("subtopic::gp::b".to_string(), 102),
            ("subtopic::gp::c".to_string(), 103),
            ("subtopic::uv::x".to_string(), 201),
        ]);
        // subtopic decks -> unit decks (10, 20) -> root (1) -> top (0)
        let parent = HashMap::from([
            (101i64, 10i64),
            (102, 10),
            (103, 10),
            (201, 20),
            (10, 1),
            (20, 1),
            (1, 0),
        ]);
        // Per-subtopic (leaf) due counts. The unit/root rolled-up counts are set
        // to a sentinel (99) that the plan MUST ignore: a tier row now sums only
        // its in-pool subtopics, never the parent deck's rolled-up total.
        let counts = HashMap::from([
            (101i64, (1u32, 0u32, 0u32, 3u32)), // gp::a WithinUnit
            (102, (2, 0, 0, 3)),                // gp::b WithinUnit
            (103, (2, 0, 0, 2)),                // gp::c Blocked
            (201, (1, 1, 0, 4)),                // uv::x CrossUnit
            (10, (99, 99, 99, 99)),             // gp unit rollup — must be ignored
            (20, (99, 99, 99, 99)),             // uv unit rollup — must be ignored
            (1, (99, 99, 99, 99)),              // root rollup — must be ignored
        ]);
        let plan = build_study_plan(&stats, &pools, &tag_deck, &counts, &parent);
        assert_eq!(plan.len(), 3, "one deck per unlocked tier");
        assert_eq!(plan[0].tier, StudyMode::Blocked);
        assert_eq!(plan[0].deck_id, 103);
        assert_eq!(plan[0].subtopic_tag.as_deref(), Some("subtopic::gp::c"));
        assert_eq!((plan[0].new, plan[0].review), (2, 0));
        // Within-unit row OPENS the unit deck (10) but its counts are the SUM of
        // the in-pool subtopics a+b = (1+2, 0, 0, 3+3), NOT the unit's rolled-up
        // 99s (which would leak the blocked subtopic c).
        assert_eq!(plan[1].tier, StudyMode::WithinUnit);
        assert_eq!(plan[1].deck_id, 10);
        assert_eq!(plan[1].unit_id.as_deref(), Some("gp"));
        assert_eq!(
            (plan[1].new, plan[1].review, plan[1].learn, plan[1].total),
            (3, 0, 0, 6)
        );
        // Cross-unit row OPENS the root (1) but its counts are ONLY the CrossUnit
        // subtopic x = (1, 1, 0, 4), not the root's rolled-up 99s.
        assert_eq!(plan[2].tier, StudyMode::CrossUnit);
        assert_eq!(plan[2].deck_id, 1);
        assert_eq!(
            (plan[2].new, plan[2].review, plan[2].learn, plan[2].total),
            (1, 1, 0, 4)
        );
    }

    #[test]
    fn study_plan_within_unit_count_excludes_blocked_subtopics() {
        // The owner's 6-not-12 case: a unit with 6 within-unit + 6 blocked
        // subtopics. The within-unit row must count ONLY the 6 promoted
        // (WithinUnit-pool) subtopics — exactly what strict-study serves — not
        // the unit deck's rolled-up 12.
        let mut stats = Vec::new();
        // 6 cleared sub-types (>=2 cleared, unit not fully mastered) -> WithinUnit.
        for i in 0..6 {
            stats.push(stat("gp", &format!("ready{i}"), 12, 12, 0.95));
        }
        // 6 still-blocked sub-types keep the unit unmastered.
        for i in 0..6 {
            stats.push(stat("gp", &format!("blocked{i}"), 0, 0, 0.0));
        }
        let pools = compute_pools(&stats);

        let mut tag_deck: HashMap<String, i64> = HashMap::new();
        let mut counts: HashMap<i64, Counts> = HashMap::new();
        let mut parent: HashMap<i64, i64> = HashMap::new();
        // Unit deck 10 -> root 1 -> top 0.
        parent.insert(10, 1);
        parent.insert(1, 0);
        let mut rolled_new = 0u32;
        for (i, s) in stats.iter().enumerate() {
            let did = 100 + i as i64;
            tag_deck.insert(s.tag(), did);
            parent.insert(did, 10);
            // 1 new card due in every subtopic (blocked AND within-unit alike).
            counts.insert(did, (1, 0, 0, 1));
            rolled_new += 1;
        }
        // The unit deck's rolled-up total counts ALL 12 subtopics (6+6). The plan
        // must NOT use this for the within-unit row.
        counts.insert(10, (rolled_new, 0, 0, rolled_new));
        counts.insert(1, (rolled_new, 0, 0, rolled_new));
        assert_eq!(rolled_new, 12, "unit rolled-up new = 12 (6 within + 6 blocked)");

        let plan = build_study_plan(&stats, &pools, &tag_deck, &counts, &parent);
        let within = plan
            .iter()
            .find(|p| p.tier == StudyMode::WithinUnit)
            .expect("a within-unit row (6 cleared sub-types to interleave)");
        assert_eq!(within.deck_id, 10, "row opens the unit deck");
        assert_eq!(
            within.new, 6,
            "within-unit counts ONLY the 6 promoted subtopics, not the unit's rolled-up 12"
        );
        // The 6 blocked subtopics still each get their own blocked row.
        let blocked = plan
            .iter()
            .filter(|p| p.tier == StudyMode::Blocked)
            .count();
        assert_eq!(blocked, 6, "each still-blocked subtopic is its own blocked row");
    }

    #[test]
    fn study_plan_omits_decks_with_nothing_due_today() {
        // A blocked subtopic whose deck has nothing due today must not appear.
        let stats = vec![stat("gp", "a", 0, 0, 0.0)];
        let pools = compute_pools(&stats);
        let tag_deck = HashMap::from([("subtopic::gp::a".to_string(), 101i64)]);
        let parent = HashMap::from([(101i64, 10i64), (10, 1), (1, 0)]);
        let counts = HashMap::from([
            (101i64, (0u32, 0u32, 0u32, 3u32)),
            (10, (0, 0, 0, 3)),
            (1, (0, 0, 0, 3)),
        ]);
        assert!(build_study_plan(&stats, &pools, &tag_deck, &counts, &parent).is_empty());
    }

    #[test]
    fn study_plan_blocked_ordered_by_importance() {
        // Two blocked subtopics with cards due: the heavier one comes first.
        let stats = vec![
            stat_w("gp", "light", 0, 0, 0.0, 1.0),
            stat_w("gp", "heavy", 0, 0, 0.0, 9.0),
        ];
        let pools = compute_pools(&stats);
        let tag_deck = HashMap::from([
            ("subtopic::gp::light".to_string(), 201i64),
            ("subtopic::gp::heavy".to_string(), 202i64),
        ]);
        let parent = HashMap::from([(201i64, 10i64), (202, 10), (10, 1), (1, 0)]);
        let counts = HashMap::from([(201i64, (1u32, 0u32, 0u32, 1u32)), (202, (1, 0, 0, 1))]);
        let plan = build_study_plan(&stats, &pools, &tag_deck, &counts, &parent);
        assert_eq!(plan.len(), 2);
        assert_eq!(plan[0].subtopic_tag.as_deref(), Some("subtopic::gp::heavy"));
        assert_eq!(plan[1].subtopic_tag.as_deref(), Some("subtopic::gp::light"));
    }

    #[test]
    fn study_plan_no_within_unit_with_only_one_cleared() {
        // One cleared sub-type isn't enough to interleave, so no within-unit tier
        // (and nothing is mastered, so no cross-unit either).
        let stats = vec![
            stat("gp", "a", 12, 12, 0.95), // cleared but ALONE -> Blocked pool
            stat("gp", "b", 0, 0, 0.0),    // blocked
        ];
        let pools = compute_pools(&stats);
        assert_eq!(
            pools["subtopic::gp::a"],
            Pool::Blocked,
            "a lone cleared sub-type isn't within-unit (nothing to interleave)"
        );
        let tag_deck = HashMap::from([
            ("subtopic::gp::a".to_string(), 101i64),
            ("subtopic::gp::b".to_string(), 102i64),
        ]);
        let parent = HashMap::from([(101i64, 10i64), (102, 10), (10, 1), (1, 0)]);
        let counts = HashMap::from([
            (101i64, (1u32, 0u32, 0u32, 1u32)),
            (102, (1, 0, 0, 1)),
            (10, (2, 0, 0, 2)),
            (1, (2, 0, 0, 2)),
        ]);
        let plan = build_study_plan(&stats, &pools, &tag_deck, &counts, &parent);
        assert_eq!(plan.len(), 1);
        assert_eq!(plan[0].tier, StudyMode::Blocked);
        assert_eq!(plan[0].subtopic_tag.as_deref(), Some("subtopic::gp::b"));
    }

    // --- mastery pace vs exam date ---

    fn approx_eq(a: f64, b: f64) {
        assert!((a - b).abs() < 1e-9, "expected {b}, got {a}");
    }

    #[test]
    fn mastery_pace_on_track_when_current_rate_finishes_in_time() {
        // 5 mastered over 14 days -> 2.5/week; 10 left projects 28 days; exam in
        // 40 -> on track.
        let p = compute_mastery_pace(10, 5, 14, 40, true);
        approx_eq(p.current_per_week, 2.5);
        assert_eq!(p.projected_days_to_finish, 28); // ceil(10 * 14 / 5)
        assert!(p.on_track);
        approx_eq(p.recommended_per_week, 10.0 / (40.0 / 7.0));
    }

    #[test]
    fn mastery_pace_behind_needs_a_higher_rate() {
        // 2 mastered over 14 days -> 1/week; 10 left projects 70 days; exam in
        // 40 -> behind, and the needed weekly rate is higher than current.
        let p = compute_mastery_pace(10, 2, 14, 40, true);
        approx_eq(p.current_per_week, 1.0);
        assert_eq!(p.projected_days_to_finish, 70); // ceil(10 * 14 / 2)
        assert!(!p.on_track);
        assert!(p.recommended_per_week > p.current_per_week);
    }

    #[test]
    fn mastery_pace_done_when_nothing_left() {
        // Whole syllabus mastered -> trivially on track, no projection.
        let p = compute_mastery_pace(0, 19, 30, 10, true);
        assert_eq!(p.projected_days_to_finish, 0);
        approx_eq(p.recommended_per_week, 0.0);
        assert!(p.on_track);
    }

    #[test]
    fn mastery_pace_never_on_track_without_an_exam_date() {
        // No exam date -> we never claim on/off track (and never invent one),
        // but the observed rate is still reported.
        let p = compute_mastery_pace(10, 5, 14, 0, false);
        approx_eq(p.current_per_week, 2.5);
        approx_eq(p.recommended_per_week, 0.0);
        assert!(!p.on_track);
    }

    #[test]
    fn mastery_pace_abstains_with_too_little_history() {
        // Something mastered but < a week of history -> we do NOT extrapolate a
        // rate or a finish date (one fast day can't fake a pace).
        let p = compute_mastery_pace(10, 3, 3, 40, true);
        approx_eq(p.current_per_week, 0.0);
        assert_eq!(p.projected_days_to_finish, 0);
        assert!(!p.on_track);
        // The needed rate is still shown (it doesn't depend on history).
        assert!(p.recommended_per_week > 0.0);
    }

    #[test]
    fn mastery_pace_abstains_when_nothing_mastered_yet() {
        // Long history but nothing cleared -> rate undefined, so no projection.
        let p = compute_mastery_pace(19, 0, 60, 40, true);
        approx_eq(p.current_per_week, 0.0);
        assert_eq!(p.projected_days_to_finish, 0);
        assert!(!p.on_track);
    }

    #[test]
    fn mastery_pace_exam_past_is_never_on_track() {
        // days_left <= 0 -> never on track, and no recommended rate.
        let p = compute_mastery_pace(10, 5, 14, -2, true);
        approx_eq(p.recommended_per_week, 0.0);
        assert!(!p.on_track);
    }

    #[test]
    fn parse_tag_handles_good_and_bad() {
        assert_eq!(
            parse_subtopic_tag("subtopic::univariate::binomial"),
            Some(("univariate".into(), "binomial".into()))
        );
        assert_eq!(parse_subtopic_tag("unit::univariate"), None);
        assert_eq!(parse_subtopic_tag("subtopic::onlyunit"), None);
    }

    // --- strict tier study (a tier serves ONLY its own pool, no leak) ---

    #[test]
    fn pool_eligible_for_tier_truth_table() {
        use Pool::*;
        // Within-unit study serves ONLY WithinUnit-pool subtopics.
        assert!(pool_eligible_for_tier(WithinUnit, TierScope::WithinUnit));
        assert!(!pool_eligible_for_tier(Blocked, TierScope::WithinUnit));
        assert!(!pool_eligible_for_tier(CrossUnit, TierScope::WithinUnit));
        // Cross-unit study serves ONLY CrossUnit-pool subtopics.
        assert!(pool_eligible_for_tier(CrossUnit, TierScope::CrossUnit));
        assert!(!pool_eligible_for_tier(Blocked, TierScope::CrossUnit));
        assert!(!pool_eligible_for_tier(WithinUnit, TierScope::CrossUnit));
    }

    #[test]
    fn strict_within_unit_serves_only_within_unit_pool() {
        // Opening a unit deck for within-unit study must serve ONLY that unit's
        // promoted (WithinUnit) sub-types: a still-Blocked sibling must NOT leak
        // in (the bug), and a CrossUnit card is out of this tier too. A card
        // with no syllabus subtopic is always kept (only the tier is scoped).
        let pools = HashMap::from([
            ("subtopic::gp::blocked".to_string(), Pool::Blocked),
            ("subtopic::gp::ready1".to_string(), Pool::WithinUnit),
            ("subtopic::gp::ready2".to_string(), Pool::WithinUnit),
            ("subtopic::uv::done".to_string(), Pool::CrossUnit),
        ]);
        let cards = vec![
            (CardId(1), Some("subtopic::gp::blocked".to_string())),
            (CardId(2), Some("subtopic::gp::ready1".to_string())),
            (CardId(3), Some("subtopic::gp::ready2".to_string())),
            (CardId(4), Some("subtopic::uv::done".to_string())),
            (CardId(5), None),
        ];
        let kept = scope_cards_to_tier(&cards, &pools, TierScope::WithinUnit);
        // Promoted within-unit cards + the untagged card, in input order.
        assert_eq!(kept, vec![CardId(2), CardId(3), CardId(5)]);
        assert!(
            !kept.contains(&CardId(1)),
            "a still-blocked subtopic must never be served in the within-unit tier"
        );
        assert!(
            !kept.contains(&CardId(4)),
            "a cross-unit subtopic is out of the within-unit tier"
        );
    }

    #[test]
    fn strict_cross_unit_serves_only_cross_unit_pool() {
        // Opening the root deck for cross-unit study must serve ONLY CrossUnit-
        // pool subtopics: both Blocked AND WithinUnit cards are excluded.
        let pools = HashMap::from([
            ("subtopic::gp::blocked".to_string(), Pool::Blocked),
            ("subtopic::gp::ready".to_string(), Pool::WithinUnit),
            ("subtopic::uv::done".to_string(), Pool::CrossUnit),
        ]);
        let cards = vec![
            (CardId(1), Some("subtopic::gp::blocked".to_string())),
            (CardId(2), Some("subtopic::gp::ready".to_string())),
            (CardId(3), Some("subtopic::uv::done".to_string())),
            (CardId(4), None),
        ];
        let kept = scope_cards_to_tier(&cards, &pools, TierScope::CrossUnit);
        assert_eq!(kept, vec![CardId(3), CardId(4)]);
        assert!(!kept.contains(&CardId(1)), "blocked must not leak into cross-unit");
        assert!(!kept.contains(&CardId(2)), "within-unit must not leak into cross-unit");
    }

    #[test]
    fn strict_tier_drops_unknown_syllabus_but_keeps_untagged() {
        // A syllabus card whose subtopic isn't classified is dropped ("serve
        // ONLY the in-tier subtopics"); a non-syllabus (untagged) card is kept.
        let pools = HashMap::from([("subtopic::uv::done".to_string(), Pool::CrossUnit)]);
        let cards = vec![
            (CardId(1), Some("subtopic::mystery::z".to_string())), // not in pools
            (CardId(2), Some("subtopic::uv::done".to_string())),
            (CardId(3), None),
        ];
        let kept = scope_cards_to_tier(&cards, &pools, TierScope::CrossUnit);
        assert_eq!(kept, vec![CardId(2), CardId(3)]);
    }

    // --- live-queue integration (the opt-in three-tier mastery scheduler) ---

    fn add_tagged(col: &mut Collection, tags: &[&str]) -> (CardId, NoteId) {
        let mut note = NoteAdder::basic(col).note();
        note.tags = tags.iter().map(|s| s.to_string()).collect();
        col.add_note(&mut note, DeckId(1)).unwrap();
        let cid: i64 = col
            .storage
            .db
            .query_row("select id from cards where nid = ?", [note.id.0], |r| {
                r.get(0)
            })
            .unwrap();
        (CardId(cid), note.id)
    }

    fn nc(id: CardId, note_id: NoteId) -> NewCard {
        NewCard {
            id,
            note_id,
            ..Default::default()
        }
    }

    #[test]
    fn mastery_scheduler_flag_defaults_off_and_is_settable() {
        let mut col = Collection::new();
        assert!(!col.speedrun_mastery_scheduler_enabled());
        col.set_config_json(MASTERY_SCHEDULER_KEY, &true, false)
            .unwrap();
        assert!(col.speedrun_mastery_scheduler_enabled());
    }

    #[test]
    fn reorder_groups_blocked_subtopics_and_puts_untagged_last() {
        // All cards are new/unreviewed, so every subtopic is Blocked. The tier
        // ordering then groups blocked cards by subtopic tag, and cards with no
        // subtopic tag sort last (non-syllabus cards are never reordered ahead).
        let mut col = Collection::new();
        let (cb1, nb1) = add_tagged(&mut col, &["subtopic::gp::b"]);
        let (cx1, nx1) = add_tagged(&mut col, &["subtopic::uv::x"]);
        let (cb2, nb2) = add_tagged(&mut col, &["subtopic::gp::b"]);
        let (cu, nu) = add_tagged(&mut col, &[]); // no subtopic tag

        let mut new = vec![nc(cx1, nx1), nc(cb1, nb1), nc(cu, nu), nc(cb2, nb2)];
        col.speedrun_reorder_new_cards(&mut new).unwrap();

        let ids: Vec<CardId> = new.iter().map(|c| c.id).collect();
        // "subtopic::gp::b" < "subtopic::uv::x", grouped; untagged card last.
        assert_eq!(ids, vec![cb1, cb2, cx1, cu]);
    }

    #[test]
    fn reorder_is_noop_without_syllabus_cards() {
        let mut col = Collection::new();
        let (c1, n1) = add_tagged(&mut col, &["leech"]);
        let (c2, n2) = add_tagged(&mut col, &[]);
        let mut new = vec![nc(c2, n2), nc(c1, n1)];
        let before: Vec<CardId> = new.iter().map(|c| c.id).collect();
        col.speedrun_reorder_new_cards(&mut new).unwrap();
        let after: Vec<CardId> = new.iter().map(|c| c.id).collect();
        assert_eq!(before, after, "non-syllabus queues must be left untouched");
    }

    #[test]
    fn build_queues_runs_with_mastery_scheduler_on() {
        // The live hook must build a valid queue (and not drop cards) when the
        // flag is on. Reordering is read-only, so this also exercises that the
        // queue build stays intact end to end.
        let mut col = Collection::new();
        add_tagged(&mut col, &["subtopic::gp::b"]);
        add_tagged(&mut col, &["subtopic::uv::x"]);
        col.set_config_json(MASTERY_SCHEDULER_KEY, &true, false)
            .unwrap();
        col.set_current_deck(DeckId(1)).unwrap();
        let queued = col.get_queued_cards(5, false).unwrap();
        assert_eq!(queued.cards.len(), 2);
    }

    #[test]
    fn scope_queues_excludes_blocked_and_is_deck_keyed() {
        // End to end through the config: all cards are fresh, so every subtopic
        // is Blocked. Scoping the studied deck to the cross-unit tier must serve
        // NOTHING (a still-blocked subtopic must not leak into cross-unit), and
        // the scope only applies to the exact deck it was keyed to.
        let mut col = Collection::new();
        let (ca, na) = add_tagged(&mut col, &["subtopic::gp::a"]);
        let (cb, nb) = add_tagged(&mut col, &["subtopic::uv::x"]);
        let studied = DeckId(1); // add_tagged adds cards to deck 1

        col.set_config_json(
            ACTIVE_TIER_SCOPE_KEY,
            &serde_json::json!({"deck_id": studied.0, "tier": "cross_unit"}),
            false,
        )
        .unwrap();

        // Reads the config, computes pools, and drops the out-of-tier cards.
        let mut new = vec![nc(ca, na), nc(cb, nb)];
        let mut review: Vec<DueCard> = Vec::new();
        col.speedrun_scope_queues_to_tier(studied, &mut new, &mut review)
            .unwrap();
        assert!(
            new.is_empty(),
            "cross-unit study must not serve still-blocked subtopics"
        );

        // Deck-keyed: the same scope must be a no-op for a different deck.
        let mut new_other = vec![nc(ca, na), nc(cb, nb)];
        col.speedrun_scope_queues_to_tier(DeckId(999), &mut new_other, &mut review)
            .unwrap();
        assert_eq!(
            new_other.len(),
            2,
            "a scope keyed to another deck must not affect this one"
        );
    }

    #[test]
    fn scope_queues_no_scope_is_a_noop() {
        // With no active tier scope, the queue is left exactly as built (the
        // parent-deck behaviour upstream / plain Anki relies on).
        let mut col = Collection::new();
        let (ca, na) = add_tagged(&mut col, &["subtopic::gp::a"]);
        let mut new = vec![nc(ca, na)];
        let mut review: Vec<DueCard> = Vec::new();
        col.speedrun_scope_queues_to_tier(DeckId(1), &mut new, &mut review)
            .unwrap();
        assert_eq!(new.len(), 1, "no scope -> nothing is dropped");
    }

    #[test]
    fn scope_queues_is_read_only() {
        // Scoping only drops in-memory gathered cards; it must write nothing, so
        // undo and collection integrity are untouched.
        let mut col = Collection::new();
        let (ca, na) = add_tagged(&mut col, &["subtopic::gp::a"]);
        col.set_config_json(
            ACTIVE_TIER_SCOPE_KEY,
            &serde_json::json!({"deck_id": 1, "tier": "cross_unit"}),
            false,
        )
        .unwrap();
        // Warm up Anki's lazy timing cache first (its one-time UTC-offset /
        // rollover config init is unrelated to scoping), so the delta below
        // isolates writes from OUR method — which must be none.
        col.timing_today().unwrap();
        let before = col.changes_since_open().unwrap();
        let mut new = vec![nc(ca, na)];
        let mut review: Vec<DueCard> = Vec::new();
        col.speedrun_scope_queues_to_tier(DeckId(1), &mut new, &mut review)
            .unwrap();
        let after = col.changes_since_open().unwrap();
        assert_eq!(before, after, "tier scoping must not modify the collection");
    }

    // --- points-at-stake review order (topic weight x student weakness) ---

    #[test]
    fn points_at_stake_orders_by_weight_times_weakness() {
        let weights = HashMap::from([
            ("subtopic::gp::a".to_string(), 9.0),
            ("subtopic::gp::b".to_string(), 1.0),
        ]);
        let weakness = HashMap::from([
            ("subtopic::gp::a".to_string(), 0.5), // stakes 9 * 0.5 = 4.5
            ("subtopic::gp::b".to_string(), 0.9), // stakes 1 * 0.9 = 0.9
        ]);
        let cards = vec![
            (CardId(1), "subtopic::gp::b".to_string(), 0.5),
            (CardId(2), "subtopic::gp::a".to_string(), 0.5),
        ];
        let out = points_at_stake_order(&cards, &weights, &weakness);
        assert_eq!(out[0].card_id, CardId(2));
        assert!((out[0].stakes - 4.5).abs() < 1e-9);
        assert!(out[0].stakes > out[1].stakes);
    }

    #[test]
    fn points_at_stake_breaks_ties_by_urgency() {
        // Same subtopic (same stakes) -> the more-urgent card (lower
        // retrievability) comes first.
        let weights = HashMap::from([("subtopic::u::x".to_string(), 5.0)]);
        let weakness = HashMap::from([("subtopic::u::x".to_string(), 0.4)]);
        let cards = vec![
            (CardId(1), "subtopic::u::x".to_string(), 0.9), // less urgent
            (CardId(2), "subtopic::u::x".to_string(), 0.2), // more urgent
        ];
        let out = points_at_stake_order(&cards, &weights, &weakness);
        assert_eq!(out[0].card_id, CardId(2));
        assert_eq!(out[1].card_id, CardId(1));
    }

    #[test]
    fn points_at_stake_equal_weight_is_weakest_topic_first() {
        // No weights supplied -> equal weighting -> order by weakness alone,
        // i.e. the weakest topic's card comes first.
        let weights = HashMap::new();
        let weakness = HashMap::from([
            ("subtopic::u::weak".to_string(), 0.8),
            ("subtopic::u::strong".to_string(), 0.1),
        ]);
        let cards = vec![
            (CardId(1), "subtopic::u::strong".to_string(), 0.9),
            (CardId(2), "subtopic::u::weak".to_string(), 0.2),
        ];
        let out = points_at_stake_order(&cards, &weights, &weakness);
        assert_eq!(out[0].card_id, CardId(2));
    }

    #[test]
    fn subtopic_weakness_is_measured_or_neutral() {
        // Retention evidence -> weakness = 1 - mean retrievability.
        let s = stat_w("u", "x", 12, 12, 0.9, 5.0);
        assert!((subtopic_weakness(&s) - 0.1).abs() < 1e-9);
        // No evidence -> neutral 0.5, never a guessed value.
        let mut s0 = stat("u", "y", 0, 0, 0.0);
        s0.retr_count = 0;
        assert_eq!(subtopic_weakness(&s0), 0.5);
    }

    // --- topic-aware live review scheduling (points-at-stake queue) ---

    fn review_card(col: &mut Collection, tags: &[&str]) -> DueCard {
        let (id, note_id) = add_tagged(col, tags);
        DueCard {
            id,
            note_id,
            mtime: TimestampSecs(0),
            due: 0,
            current_deck_id: DeckId(1),
            original_deck_id: DeckId(0),
            kind: DueCardKind::Review,
            reps: 0,
        }
    }

    #[test]
    fn points_at_stake_flag_defaults_off_and_is_settable() {
        let mut col = Collection::new();
        assert!(!col.speedrun_points_at_stake_enabled());
        col.set_config_json(POINTS_AT_STAKE_KEY, &true, false)
            .unwrap();
        assert!(col.speedrun_points_at_stake_enabled());
    }

    #[test]
    fn points_at_stake_reorders_review_by_weight() {
        // With configured weights and no FSRS evidence (weakness 0.5 for all),
        // the heavier topic's card sorts first — high-value weak-topic cards
        // come back sooner.
        let mut col = Collection::new();
        let weights = HashMap::from([
            ("subtopic::gp::a".to_string(), 9.0f64),
            ("subtopic::gp::b".to_string(), 1.0f64),
        ]);
        col.set_config_json(SUBTOPIC_WEIGHTS_KEY, &weights, false)
            .unwrap();
        let b = review_card(&mut col, &["subtopic::gp::b"]);
        let a = review_card(&mut col, &["subtopic::gp::a"]);
        let mut review = vec![b, a];
        col.speedrun_reorder_review_cards(&mut review).unwrap();
        assert_eq!(review[0].id, a.id);
        assert_eq!(review[1].id, b.id);
    }

    #[test]
    fn points_at_stake_review_reorder_is_noop_without_weights() {
        // No weights configured + no FSRS retention -> equal stakes -> the
        // review order is left untouched.
        let mut col = Collection::new();
        let a = review_card(&mut col, &["subtopic::gp::a"]);
        let b = review_card(&mut col, &["subtopic::gp::b"]);
        let mut review = vec![a, b];
        let before: Vec<CardId> = review.iter().map(|c| c.id).collect();
        col.speedrun_reorder_review_cards(&mut review).unwrap();
        let after: Vec<CardId> = review.iter().map(|c| c.id).collect();
        assert_eq!(before, after);
    }

    #[test]
    fn build_queues_runs_with_points_at_stake_on() {
        let mut col = Collection::new();
        add_tagged(&mut col, &["subtopic::gp::a"]);
        col.set_config_json(POINTS_AT_STAKE_KEY, &true, false)
            .unwrap();
        col.set_current_deck(DeckId(1)).unwrap();
        // Builds a valid queue with the flag on (review queue may be empty).
        let _ = col.get_queued_cards(5, false).unwrap();
    }

    // --- mastery-tier ordering of the REVIEW queue (blocked practice carries
    // through reviews until a subtopic clears its gate) ---

    #[test]
    fn review_tier_reorder_groups_blocked_subtopics_and_puts_untagged_last() {
        // All cards are unreviewed, so every subtopic is Blocked. The review
        // reorder then groups blocked cards by subtopic (same as new cards), and
        // cards with no subtopic tag sort last — so a not-yet-mastered subtopic's
        // due reviews are drilled together rather than scattered.
        let mut col = Collection::new();
        let b1 = review_card(&mut col, &["subtopic::gp::b"]);
        let x1 = review_card(&mut col, &["subtopic::uv::x"]);
        let b2 = review_card(&mut col, &["subtopic::gp::b"]);
        let u = review_card(&mut col, &[]); // no subtopic tag

        let mut review = vec![x1, b1, u, b2];
        col.speedrun_reorder_review_cards_by_tier(&mut review)
            .unwrap();

        let ids: Vec<CardId> = review.iter().map(|c| c.id).collect();
        // "subtopic::gp::b" < "subtopic::uv::x", grouped; untagged card last.
        assert_eq!(ids, vec![b1.id, b2.id, x1.id, u.id]);
    }

    #[test]
    fn review_tier_reorder_is_noop_without_syllabus_cards() {
        let mut col = Collection::new();
        let c1 = review_card(&mut col, &["leech"]);
        let c2 = review_card(&mut col, &[]);
        let mut review = vec![c2, c1];
        let before: Vec<CardId> = review.iter().map(|c| c.id).collect();
        col.speedrun_reorder_review_cards_by_tier(&mut review)
            .unwrap();
        let after: Vec<CardId> = review.iter().map(|c| c.id).collect();
        assert_eq!(before, after, "non-syllabus review queues stay untouched");
    }

    // --- guided-learning gate (the prerequisite DAG) ---

    fn perf_cell(questions: u32, correct: u32) -> Performance {
        Performance { questions, correct }
    }

    #[test]
    fn performance_mastered_needs_sample_and_accuracy() {
        assert!(perf_cell(5, 4).mastered()); // 5 Q at 80%
        assert!(!perf_cell(4, 4).mastered()); // too few questions
        assert!(!perf_cell(10, 7).mastered()); // 70% < 80%
        assert!(!perf_cell(0, 0).mastered()); // abstains with no sample
    }

    #[test]
    fn locks_gate_downstream_until_prereqs_are_satisfied() {
        // a -> b -> c chain, nothing cleared: a is open, b and c are locked.
        let stats = vec![
            stat("u", "a", 0, 0, 0.0),
            stat("u", "b", 0, 0, 0.0),
            stat("u", "c", 0, 0, 0.0),
        ];
        let prereqs = HashMap::from([
            ("subtopic::u::a".to_string(), vec![]),
            (
                "subtopic::u::b".to_string(),
                vec!["subtopic::u::a".to_string()],
            ),
            (
                "subtopic::u::c".to_string(),
                vec!["subtopic::u::b".to_string()],
            ),
        ]);
        let perf = HashMap::new();
        let unlocked = std::collections::HashSet::new();
        let locks = compute_locks(&stats, &perf, &prereqs, &HashMap::new(), &unlocked, true);
        assert!(!locks["subtopic::u::a"].locked);
        assert!(locks["subtopic::u::b"].locked);
        assert!(locks["subtopic::u::c"].locked);

        // Clear a via the MEMORY gate: b opens, c stays locked.
        let stats2 = vec![
            stat("u", "a", 12, 12, 0.95),
            stat("u", "b", 0, 0, 0.0),
            stat("u", "c", 0, 0, 0.0),
        ];
        let locks2 = compute_locks(&stats2, &perf, &prereqs, &HashMap::new(), &unlocked, true);
        assert!(!locks2["subtopic::u::b"].locked);
        assert!(locks2["subtopic::u::c"].locked);
    }

    #[test]
    fn in_progress_prereq_unlocks_downstream() {
        // Softened gate: `a` is STARTED (studied) but NOT fully mastered (too few
        // reviews, low retention). Its dependent `b` should still unlock, so a
        // learner isn't blocked waiting to master `a` before ever seeing `b`.
        let prereqs = HashMap::from([
            ("subtopic::u::a".to_string(), vec![]),
            (
                "subtopic::u::b".to_string(),
                vec!["subtopic::u::a".to_string()],
            ),
        ]);
        let empty_unlocked = std::collections::HashSet::new();

        let in_progress = vec![stat("u", "a", 3, 2, 0.5), stat("u", "b", 0, 0, 0.0)];
        assert!(!in_progress[0].gate_cleared(), "a is not fully mastered");
        let locks = compute_locks(
            &in_progress,
            &HashMap::new(),
            &prereqs,
            &HashMap::new(),
            &empty_unlocked,
            true,
        );
        assert!(
            !locks["subtopic::u::b"].locked,
            "started prereq should unlock its dependent"
        );

        // A truly UNSTARTED prereq (0 reviews) still locks its dependent.
        let unstarted = vec![stat("u", "a", 0, 0, 0.0), stat("u", "b", 0, 0, 0.0)];
        let locks2 = compute_locks(
            &unstarted,
            &HashMap::new(),
            &prereqs,
            &HashMap::new(),
            &empty_unlocked,
            true,
        );
        assert!(
            locks2["subtopic::u::b"].locked,
            "unstarted prereq still gates"
        );
    }

    #[test]
    fn performance_can_satisfy_a_prereq_without_flashcards() {
        // a is NOT memory-cleared, but is performance-mastered -> b unlocks.
        let stats = vec![stat("u", "a", 0, 0, 0.0), stat("u", "b", 0, 0, 0.0)];
        let prereqs = HashMap::from([(
            "subtopic::u::b".to_string(),
            vec!["subtopic::u::a".to_string()],
        )]);
        let perf = HashMap::from([("subtopic::u::a".to_string(), perf_cell(10, 9))]);
        let locks = compute_locks(
            &stats,
            &perf,
            &prereqs,
            &HashMap::new(),
            &std::collections::HashSet::new(),
            true,
        );
        assert!(!locks["subtopic::u::b"].locked);
        assert!(locks["subtopic::u::b"].unmet_prereqs.is_empty());
    }

    #[test]
    fn unit_prereqs_gate_whole_units() {
        // uv depends on gp; gp has one unfinished subtopic -> uv is locked.
        let stats = vec![
            stat("gp", "a", 12, 12, 0.95),
            stat("gp", "b", 0, 0, 0.0), // gp not finished
            stat("uv", "x", 0, 0, 0.0),
        ];
        let unit_prereqs = HashMap::from([("uv".to_string(), vec!["gp".to_string()])]);
        let locks = compute_locks(
            &stats,
            &HashMap::new(),
            &HashMap::new(),
            &unit_prereqs,
            &std::collections::HashSet::new(),
            true,
        );
        assert!(locks["subtopic::uv::x"].locked);
        assert!(locks["subtopic::uv::x"]
            .unmet_prereqs
            .contains(&"subtopic::gp::b".to_string()));

        // Finish gp -> uv opens.
        let stats2 = vec![
            stat("gp", "a", 12, 12, 0.95),
            stat("gp", "b", 12, 12, 0.95),
            stat("uv", "x", 0, 0, 0.0),
        ];
        let locks2 = compute_locks(
            &stats2,
            &HashMap::new(),
            &HashMap::new(),
            &unit_prereqs,
            &std::collections::HashSet::new(),
            true,
        );
        assert!(!locks2["subtopic::uv::x"].locked);
    }

    #[test]
    fn free_mode_and_unlock_bypass_the_gate() {
        let stats = vec![stat("u", "a", 0, 0, 0.0), stat("u", "b", 0, 0, 0.0)];
        let prereqs = HashMap::from([(
            "subtopic::u::b".to_string(),
            vec!["subtopic::u::a".to_string()],
        )]);
        // Free mode (guided = false): nothing locked, but unmet is still reported
        // so the map can show the recommended order.
        let free = compute_locks(
            &stats,
            &HashMap::new(),
            &prereqs,
            &HashMap::new(),
            &std::collections::HashSet::new(),
            false,
        );
        assert!(!free["subtopic::u::b"].locked);
        assert_eq!(
            free["subtopic::u::b"].unmet_prereqs,
            vec!["subtopic::u::a".to_string()]
        );
        // Per-topic unlock: b is unlocked -> not locked even under guided mode.
        let unlocked = std::collections::HashSet::from(["subtopic::u::b".to_string()]);
        let g = compute_locks(
            &stats,
            &HashMap::new(),
            &prereqs,
            &HashMap::new(),
            &unlocked,
            true,
        );
        assert!(!g["subtopic::u::b"].locked);
    }

    #[test]
    fn guided_gate_defaults_on_and_is_settable() {
        let mut col = Collection::new();
        assert!(col.speedrun_guided_mode_enabled()); // default ON
        col.set_config_json(GUIDED_MODE_KEY, &false, false).unwrap();
        assert!(!col.speedrun_guided_mode_enabled());
    }

    #[test]
    fn gate_withholds_locked_new_cards_but_keeps_open_ones() {
        // DAG a -> b, guided default on. Only a's new cards survive the gate.
        let mut col = Collection::new();
        let (ca, na) = add_tagged(&mut col, &["subtopic::u::a"]);
        let (cb, nb) = add_tagged(&mut col, &["subtopic::u::b"]);
        let prereqs = HashMap::from([
            ("subtopic::u::a".to_string(), Vec::<String>::new()),
            (
                "subtopic::u::b".to_string(),
                vec!["subtopic::u::a".to_string()],
            ),
        ]);
        col.set_config_json(SUBTOPIC_PREREQS_KEY, &prereqs, false)
            .unwrap();

        let mut new = vec![nc(ca, na), nc(cb, nb)];
        col.speedrun_gate_new_cards(&mut new).unwrap();
        let ids: Vec<CardId> = new.iter().map(|c| c.id).collect();
        assert_eq!(ids, vec![ca], "b is locked until a is satisfied");

        // Free mode -> the caller's guard skips the gate, so everything flows.
        col.set_config_json(GUIDED_MODE_KEY, &false, false).unwrap();
        let mut new2 = vec![nc(ca, na), nc(cb, nb)];
        if col.speedrun_guided_mode_enabled() {
            col.speedrun_gate_new_cards(&mut new2).unwrap();
        }
        let ids2: Vec<CardId> = new2.iter().map(|c| c.id).collect();
        assert_eq!(ids2, vec![ca, cb], "free mode serves everything");
    }

    #[test]
    fn gate_is_noop_without_a_dag() {
        // No prereq config -> the gate drops no card (upstream / plain decks).
        let mut col = Collection::new();
        let (ca, na) = add_tagged(&mut col, &["subtopic::u::a"]);
        let (cb, nb) = add_tagged(&mut col, &["subtopic::u::b"]);
        let mut new = vec![nc(ca, na), nc(cb, nb)];
        col.speedrun_gate_new_cards(&mut new).unwrap();
        assert_eq!(new.len(), 2);
    }

    #[test]
    fn build_queues_gates_new_cards_when_guided() {
        // End-to-end: with a DAG configured and guided mode default-on, the live
        // queue serves only the unlocked subtopic's new card.
        let mut col = Collection::new();
        add_tagged(&mut col, &["subtopic::u::a"]);
        add_tagged(&mut col, &["subtopic::u::b"]);
        let prereqs = HashMap::from([
            ("subtopic::u::a".to_string(), Vec::<String>::new()),
            (
                "subtopic::u::b".to_string(),
                vec!["subtopic::u::a".to_string()],
            ),
        ]);
        col.set_config_json(SUBTOPIC_PREREQS_KEY, &prereqs, false)
            .unwrap();
        col.set_current_deck(DeckId(1)).unwrap();
        let queued = col.get_queued_cards(5, false).unwrap();
        assert_eq!(queued.cards.len(), 1, "b's new card is gated out");
    }
}
