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

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Pool {
    /// Not yet mastered — practice this subtopic in isolation.
    Blocked,
    /// Cleared, but its unit isn't fully mastered — interleave within the unit.
    WithinUnit,
    /// Its unit is mastered — interleave across units (spacing).
    CrossUnit,
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
    /// Relative importance weight from the topic map (0 when none supplied).
    /// Set by the caller from the request; used only for the weighted rollup.
    pub weight: f64,
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

    /// The subtopic gate: enough graded problems, accurate, and well-retained.
    pub(crate) fn gate_cleared(&self) -> bool {
        self.reviews >= MIN_PROBLEMS
            && self.accuracy() >= MIN_ACCURACY
            && self.mean_retrievability() >= MIN_RETRIEVABILITY
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

/// Multi-level gating: a subtopic's pool depends on its own gate AND whether
/// its whole unit has been mastered (every subtopic in the unit cleared).
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
            let pool = if !s.gate_cleared() {
                Pool::Blocked
            } else if unit_mastered(&s.unit_id) {
                Pool::CrossUnit
            } else {
                Pool::WithinUnit
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
    gate: &HashMap<String, bool>,
    perf: &HashMap<String, Performance>,
) -> bool {
    // Unknown prereq (not among the syllabus stats): fail OPEN so a data gap
    // can't permanently lock the tree. Known prereqs must actually be satisfied.
    let Some(&cleared) = gate.get(tag) else {
        return true;
    };
    cleared || perf.get(tag).map(|p| p.mastered()).unwrap_or(false)
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
            Some(tags) if !tags.is_empty() => tags.iter().all(|t| prereq_satisfied(t, &gate, perf)),
            _ => true,
        }
    };
    // A representative not-yet-satisfied subtopic of a unit, for the lock reason.
    let unit_blocker = |unit: &str| -> Option<String> {
        unit_subs
            .get(unit)?
            .iter()
            .find(|t| !prereq_satisfied(t, &gate, perf))
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
                    if !prereq_satisfied(p, &gate, perf) {
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
/// `not_started` with zero reviews, `mastered` once its gate is cleared, and
/// `in_progress` otherwise; the three partition the syllabus so nothing is
/// double-counted or invented. A unit is mastered when it has >= 1 subtopic and
/// all of them are cleared.
pub(crate) fn mastery_overall(stats: &[SubtopicStats]) -> MasteryOverallCounts {
    let subtopics_total = stats.len() as u32;
    let subtopics_mastered = stats.iter().filter(|s| s.gate_cleared()).count() as u32;
    let subtopics_not_started = stats.iter().filter(|s| s.reviews == 0).count() as u32;
    let subtopics_in_progress = subtopics_total
        .saturating_sub(subtopics_mastered)
        .saturating_sub(subtopics_not_started);

    let mut unit_total: HashMap<&str, u32> = HashMap::new();
    let mut unit_cleared: HashMap<&str, u32> = HashMap::new();
    for s in stats {
        *unit_total.entry(s.unit_id.as_str()).or_default() += 1;
        if s.gate_cleared() {
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
/// the share of that group's total weight that sits on gate-cleared subtopics.
/// When no weights are supplied (total weight 0) it falls back to the plain
/// cleared/total count fraction, so a caller that omits weights still gets a
/// sensible number. Every value is MEASURED demonstrated mastery, never a
/// predicted score.
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
        let cleared = s.gate_cleared();
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
        .filter(|s| s.gate_cleared())
        .map(|s| s.weight)
        .sum();
    let total_n = stats.len() as u32;
    let cleared_n = stats.iter().filter(|s| s.gate_cleared()).count() as u32;
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
            "Only {}/{} graded reviews — keep practising to build enough evidence.",
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
        if c >= 2 && c < t && best.map_or(true, |(_, bc)| c > bc) {
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

/// Build today's tiered study plan from measured gate state + real deck counts.
///
/// - BLOCKED: every uncleared subtopic (highest exam-importance first),
///   pointing at its own subtopic deck — drill it in isolation.
/// - WITHIN_UNIT: units that aren't fully mastered but have >= 2 cleared
///   sub-types to interleave, pointing at the unit deck (the parent of its
///   subtopic decks).
/// - CROSS_UNIT: once any unit is mastered, the whole-exam deck (the
///   grandparent of a subtopic deck) for cross-unit spacing.
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

    // Per-unit rollup, first-seen order.
    let mut unit_order: Vec<String> = Vec::new();
    let mut total: HashMap<String, u32> = HashMap::new();
    let mut cleared: HashMap<String, u32> = HashMap::new();
    let mut sample_deck: HashMap<String, i64> = HashMap::new();
    for s in stats {
        if !total.contains_key(&s.unit_id) {
            unit_order.push(s.unit_id.clone());
        }
        *total.entry(s.unit_id.clone()).or_default() += 1;
        if s.gate_cleared() {
            *cleared.entry(s.unit_id.clone()).or_default() += 1;
        }
        if let Some(&did) = tag_deck.get(&s.tag()) {
            sample_deck.entry(s.unit_id.clone()).or_insert(did);
        }
    }

    // WITHIN_UNIT tier: not fully mastered, >= 2 cleared sub-types to interleave.
    for unit in &unit_order {
        let t = total.get(unit).copied().unwrap_or(0);
        let c = cleared.get(unit).copied().unwrap_or(0);
        let mastered = t > 0 && c == t;
        if mastered || c < 2 {
            continue;
        }
        let Some(&sub_did) = sample_deck.get(unit) else {
            continue;
        };
        let unit_did = parent.get(&sub_did).copied().unwrap_or(0);
        if unit_did == 0 {
            continue;
        }
        if let Some(&cc) = counts.get(&unit_did).filter(|c| is_actionable(**c)) {
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

    // CROSS_UNIT tier: once a unit is mastered, interleave across units via the
    // whole-exam deck (grandparent of a subtopic deck).
    let any_cross = stats
        .iter()
        .any(|s| pools.get(&s.tag()).copied() == Some(Pool::CrossUnit));
    if any_cross {
        // All subtopics share one root, so any subtopic deck resolves it.
        let root = sample_deck.values().next().map(|&sub_did| {
            let unit_did = parent.get(&sub_did).copied().unwrap_or(0);
            parent.get(&unit_did).copied().unwrap_or(0)
        });
        if let Some(root_did) = root.filter(|&d| d != 0) {
            if let Some(&cc) = counts.get(&root_did).filter(|c| is_actionable(**c)) {
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

/// Coverage-pace arithmetic: given the new cards still to introduce, the
/// current new-cards/day limit, and days until the exam, work out the pace
/// needed and whether the current pace makes it in time.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct Pace {
    pub recommended_new_per_day: u32,
    pub projected_days_to_finish: u32,
    pub on_track: bool,
}

/// Pure pace maths (no I/O), so it can be unit-tested. Everything is a plain
/// function of MEASURED counts + the user's date; it is a syllabus-coverage
/// pace, never a predicted exam score. With nothing left to introduce the user
/// is trivially "on track". `recommended` is ceil(remaining / days_left) (or
/// all of them if the exam is today/past); `projected` is how many days the
/// current pace needs; `on_track` is true only with an exam date, a known
/// pace, and days remaining, when the projection lands on/before the exam.
pub(crate) fn compute_pace(
    remaining_new: u32,
    current_new_per_day: u32,
    days_left: i64,
    has_exam_date: bool,
) -> Pace {
    if remaining_new == 0 {
        return Pace {
            recommended_new_per_day: 0,
            projected_days_to_finish: 0,
            on_track: true,
        };
    }
    let recommended_new_per_day = if days_left > 0 {
        (remaining_new as f64 / days_left as f64).ceil() as u32
    } else {
        remaining_new
    };
    let projected_days_to_finish = if current_new_per_day > 0 {
        (remaining_new as f64 / current_new_per_day as f64).ceil() as u32
    } else {
        0
    };
    let on_track = has_exam_date
        && current_new_per_day > 0
        && days_left > 0
        && (projected_days_to_finish as i64) <= days_left;
    Pace {
        recommended_new_per_day,
        projected_days_to_finish,
        on_track,
    }
}

/// Order new cards by tier: blocked subtopics first (grouped so each is
/// practised in isolation), then within-unit interleaving, then cross-unit
/// interleaving. Cards whose subtopic is unknown sort last, preserving their
/// input order.
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
    // Grouping key within a tier: Blocked practises one subtopic at a time (group
    // by subtopic); the Full within-unit tier groups by UNIT so a unit's
    // confusable cleared subtopics stay together (this IS the within-unit
    // interleaving the ablation removes); the ablated mixed pool and the
    // cross-unit spacing tier use no grouping, so cleared cards interleave
    // globally in input order.
    let group = |r: u8, pool: Option<Pool>, tag: &str| -> String {
        if r == 0 {
            tag.to_string()
        } else if !ablate_within_unit && matches!(pool, Some(Pool::WithinUnit)) {
            parse_subtopic_tag(tag).map(|(u, _)| u).unwrap_or_default()
        } else {
            String::new()
        }
    };
    let mut keyed: Vec<(u8, String, usize, CardId)> = cards
        .iter()
        .enumerate()
        .map(|(i, (cid, tag))| {
            let pool = pools.get(tag).copied();
            let r = rank(pool);
            (r, group(r, pool, tag), i, *cid)
        })
        .collect();
    keyed.sort_by(|a, b| {
        a.0.cmp(&b.0)
            .then_with(|| a.1.cmp(&b.1))
            .then_with(|| a.2.cmp(&b.2))
    });
    keyed.into_iter().map(|(_, _, _, cid)| cid).collect()
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
        let sql = "
            SELECT c.did, n.tags
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

    /// The new-cards/day limit on the syllabus root deck (the first path
    /// segment of any subtopic deck's name, e.g. "SOA Exam P"). This is the
    /// intake cap the coverage pace projects against. `None` when no
    /// syllabus deck exists. Read-only.
    pub(crate) fn speedrun_root_new_per_day(
        &mut self,
        expected_subtopics: &[String],
    ) -> Result<Option<u32>> {
        let tag_deck = self.speedrun_subtopic_deck_ids(expected_subtopics)?;
        let Some(&sub_did) = tag_deck.values().next() else {
            return Ok(None);
        };
        let names: HashMap<i64, String> = self
            .storage
            .get_all_deck_names()?
            .into_iter()
            .map(|(id, name)| (id.0, name))
            .collect();
        let Some(full) = names.get(&sub_did) else {
            return Ok(None);
        };
        let root_name = full.split("::").next().unwrap_or(full);
        let Some(root_id) = self.get_deck_id(root_name)? else {
            return Ok(None);
        };
        let Some(deck) = self.get_deck(root_id)? else {
            return Ok(None);
        };
        let Some(config_id) = deck.config_id() else {
            return Ok(None);
        };
        let Some(config) = self.get_deck_config(config_id, true)? else {
            return Ok(None);
        };
        Ok(Some(config.inner.new_per_day))
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

    /// Reorder already-gathered new cards by mastery tier: Blocked (practise a
    /// subtopic in isolation) -> WithinUnit (interleave confusable sub-types)
    /// -> CrossUnit (spacing). Blocked subtopics are grouped so each is
    /// practised together. Cards without a subtopic tag keep their relative
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
            weight: 0.0,
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
        // Unit "gp" has two subtopics; "uv" has one.
        // gp::a cleared, gp::b not -> gp not mastered.
        let stats = vec![
            stat("gp", "a", 12, 12, 0.95),
            stat("gp", "b", 3, 1, 0.50),
            stat("uv", "x", 15, 15, 0.99),
        ];
        let pools = compute_pools(&stats);
        // gp::a cleared but unit not mastered -> WithinUnit.
        assert_eq!(pools["subtopic::gp::a"], Pool::WithinUnit);
        // gp::b not cleared -> Blocked.
        assert_eq!(pools["subtopic::gp::b"], Pool::Blocked);
        // uv fully mastered (its only subtopic cleared) -> CrossUnit.
        assert_eq!(pools["subtopic::uv::x"], Pool::CrossUnit);

        // Now clear gp::b: gp becomes mastered, so gp::a promotes to CrossUnit.
        let stats2 = vec![
            stat("gp", "a", 12, 12, 0.95),
            stat("gp", "b", 12, 11, 0.95),
            stat("uv", "x", 15, 15, 0.99),
        ];
        let pools2 = compute_pools(&stats2);
        assert_eq!(pools2["subtopic::gp::a"], Pool::CrossUnit);
        assert_eq!(pools2["subtopic::gp::b"], Pool::CrossUnit);
    }

    #[test]
    fn pool_ordering_blocked_first_then_within_then_cross() {
        let stats = vec![
            stat("gp", "a", 12, 12, 0.95), // WithinUnit (gp::b blocks the unit)
            stat("gp", "b", 0, 0, 0.0),    // Blocked
            stat("uv", "x", 15, 15, 0.99), // CrossUnit
        ];
        let pools = compute_pools(&stats);
        let cards = vec![
            (CardId(1), "subtopic::uv::x".to_string()), // CrossUnit
            (CardId(2), "subtopic::gp::a".to_string()), // WithinUnit
            (CardId(3), "subtopic::gp::b".to_string()), // Blocked
            (CardId(4), "subtopic::unknown::z".to_string()), // unknown -> last
        ];
        let ordered = order_new_cards(&cards, &pools, false);
        assert_eq!(ordered, vec![CardId(3), CardId(2), CardId(1), CardId(4)]);
    }

    #[test]
    fn full_scheduler_groups_within_unit_cleared_cards_by_unit() {
        // Two units, each with a cleared (WithinUnit) subtopic + a blocking one,
        // with cards input-interleaved across units. The FULL build groups each
        // unit's within-unit cleared cards together (within-unit interleaving);
        // the ABLATED build interleaves all cleared cards globally by input order.
        let stats = vec![
            stat("gp", "a", 12, 12, 0.95), // cleared -> WithinUnit (gp::b blocks)
            stat("gp", "b", 0, 0, 0.0),    // blocked
            stat("uv", "x", 12, 12, 0.95), // cleared -> WithinUnit (uv::y blocks)
            stat("uv", "y", 0, 0, 0.0),    // blocked
        ];
        let pools = compute_pools(&stats);
        let cards = vec![
            (CardId(1), "subtopic::gp::a".to_string()),
            (CardId(2), "subtopic::uv::x".to_string()),
            (CardId(3), "subtopic::gp::a".to_string()),
            (CardId(4), "subtopic::uv::x".to_string()),
        ];
        // Full: grouped by unit -> both gp cards, then both uv cards.
        assert_eq!(
            order_new_cards(&cards, &pools, false),
            vec![CardId(1), CardId(3), CardId(2), CardId(4)]
        );
        // Ablated: within-unit tier removed -> global interleave in input order.
        assert_eq!(
            order_new_cards(&cards, &pools, true),
            vec![CardId(1), CardId(2), CardId(3), CardId(4)]
        );
    }

    #[test]
    fn ablated_collapses_within_and_cross_into_one_mixed_pool() {
        // gp::a is WithinUnit (gp::b blocks its unit); uv::x is CrossUnit (uv is
        // fully mastered). Full serves the within-unit card before the cross-unit
        // card; ablated treats both as one mixed pool, so input order decides.
        let stats = vec![
            stat("gp", "a", 12, 12, 0.95),
            stat("gp", "b", 0, 0, 0.0),
            stat("uv", "x", 12, 12, 0.95), // uv's only subtopic -> CrossUnit
        ];
        let pools = compute_pools(&stats);
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
        // Only the blocked deck (103), the gp unit deck (10) and root (1) have
        // something due today; the rest are present but empty (must be filtered).
        let counts = HashMap::from([
            (103i64, (2u32, 0u32, 0u32, 2u32)),
            (10, (2, 1, 0, 6)),
            (1, (3, 4, 0, 8)),
            (101, (0, 0, 0, 2)),
            (102, (0, 0, 0, 2)),
            (201, (0, 0, 0, 2)),
            (20, (0, 0, 0, 2)),
        ]);
        let plan = build_study_plan(&stats, &pools, &tag_deck, &counts, &parent);
        assert_eq!(plan.len(), 3, "one deck per unlocked tier");
        assert_eq!(plan[0].tier, StudyMode::Blocked);
        assert_eq!(plan[0].deck_id, 103);
        assert_eq!(plan[0].subtopic_tag.as_deref(), Some("subtopic::gp::c"));
        assert_eq!((plan[0].new, plan[0].review), (2, 0));
        assert_eq!(plan[1].tier, StudyMode::WithinUnit);
        assert_eq!(plan[1].deck_id, 10);
        assert_eq!(plan[1].unit_id.as_deref(), Some("gp"));
        assert_eq!(plan[2].tier, StudyMode::CrossUnit);
        assert_eq!(plan[2].deck_id, 1);
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
            stat("gp", "a", 12, 12, 0.95), // cleared -> WithinUnit pool
            stat("gp", "b", 0, 0, 0.0),    // blocked
        ];
        let pools = compute_pools(&stats);
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

    // --- coverage pace vs exam date ---

    #[test]
    fn pace_on_track_when_current_rate_finishes_in_time() {
        // 100 new left, 20/day -> finish in 5 days; exam in 10 -> on track.
        let p = compute_pace(100, 20, 10, true);
        assert_eq!(p.recommended_new_per_day, 10); // ceil(100/10)
        assert_eq!(p.projected_days_to_finish, 5); // ceil(100/20)
        assert!(p.on_track);
    }

    #[test]
    fn pace_behind_needs_a_higher_rate() {
        // 100 new left, 20/day -> finish in 5 days; exam in 3 -> behind, and the
        // recommended rate rises to clear them in time.
        let p = compute_pace(100, 20, 3, true);
        assert_eq!(p.recommended_new_per_day, 34); // ceil(100/3)
        assert_eq!(p.projected_days_to_finish, 5);
        assert!(!p.on_track);
    }

    #[test]
    fn pace_done_when_nothing_left() {
        // Nothing new to introduce -> trivially on track, no pace needed.
        let p = compute_pace(0, 20, 3, true);
        assert_eq!(p.recommended_new_per_day, 0);
        assert_eq!(p.projected_days_to_finish, 0);
        assert!(p.on_track);
    }

    #[test]
    fn pace_never_on_track_without_an_exam_date() {
        // No exam date -> we never claim on/off track (and never invent one).
        let p = compute_pace(100, 20, 0, false);
        assert!(!p.on_track);
    }

    #[test]
    fn pace_exam_today_or_past_needs_all_now() {
        // days_left <= 0 -> the honest recommendation is "all of them now".
        let p = compute_pace(40, 20, 0, true);
        assert_eq!(p.recommended_new_per_day, 40);
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
