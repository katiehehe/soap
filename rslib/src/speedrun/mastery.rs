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
use crate::timestamp::TimestampSecs;

/// Pre-registered gate (PRD 8): a subtopic clears when it has been executed
/// enough times, accurately, and its memory is strong.
pub(crate) const MIN_PROBLEMS: u32 = 10;
pub(crate) const MIN_ACCURACY: f64 = 0.80;
pub(crate) const MIN_RETRIEVABILITY: f64 = 0.90;

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

/// Order new cards by tier: blocked subtopics first (grouped so each is
/// practised in isolation), then within-unit interleaving, then cross-unit
/// interleaving. Cards whose subtopic is unknown sort last, preserving their
/// input order.
pub(crate) fn order_new_cards(
    cards: &[(CardId, String)],
    pools: &HashMap<String, Pool>,
) -> Vec<CardId> {
    fn rank(pool: Option<Pool>) -> u8 {
        match pool {
            Some(Pool::Blocked) => 0,
            Some(Pool::WithinUnit) => 1,
            Some(Pool::CrossUnit) => 2,
            None => 3,
        }
    }
    // Precompute each card's tier rank once (a single hash lookup per card)
    // rather than hashing the subtopic tag inside the O(n log n) comparator,
    // which keeps ordering fast on a large new-card pool.
    let mut keyed: Vec<(u8, &str, usize, CardId)> = cards
        .iter()
        .enumerate()
        .map(|(i, (cid, tag))| (rank(pools.get(tag).copied()), tag.as_str(), i, *cid))
        .collect();
    keyed.sort_by(|a, b| {
        // Tier first; within Blocked, group by subtopic tag so a subtopic is
        // practised together; then fall back to stable input order.
        a.0.cmp(&b.0)
            .then_with(|| {
                if a.0 == 0 {
                    a.1.cmp(b.1)
                } else {
                    std::cmp::Ordering::Equal
                }
            })
            .then_with(|| a.2.cmp(&b.2))
    });
    keyed.into_iter().map(|(_, _, _, cid)| cid).collect()
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
}

#[cfg(test)]
mod tests {
    use super::*;

    fn stat(unit: &str, sub: &str, reviews: u32, correct: u32, mean_r: f64) -> SubtopicStats {
        SubtopicStats {
            unit_id: unit.into(),
            subtopic_id: sub.into(),
            reviews,
            correct,
            retr_sum: mean_r * reviews.max(1) as f64,
            retr_count: reviews.max(1),
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
        let ordered = order_new_cards(&cards, &pools);
        assert_eq!(ordered, vec![CardId(3), CardId(2), CardId(1), CardId(4)]);
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
    fn parse_tag_handles_good_and_bad() {
        assert_eq!(
            parse_subtopic_tag("subtopic::univariate::binomial"),
            Some(("univariate".into(), "binomial".into()))
        );
        assert_eq!(parse_subtopic_tag("unit::univariate"), None);
        assert_eq!(parse_subtopic_tag("subtopic::onlyunit"), None);
    }
}
