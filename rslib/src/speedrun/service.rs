// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

use std::collections::HashMap;

use anki_proto::speedrun::readiness_result;
use anki_proto::speedrun::ComputeReadinessRequest;
use anki_proto::speedrun::MasteryOrderedCards;
use anki_proto::speedrun::MasteryRequest;
use anki_proto::speedrun::MasteryState;
use anki_proto::speedrun::NoScore;
use anki_proto::speedrun::ReadinessResult;
use anki_proto::speedrun::SpeedrunPingResponse;
use anki_proto::speedrun::SubtopicMastery;
use anki_proto::speedrun::UnitMastery;
use unicase::UniCase;

use crate::collection::Collection;
use crate::error;
use crate::speedrun::mastery::compute_pools;
use crate::speedrun::mastery::order_new_cards;
use crate::speedrun::mastery::parse_subtopic_tag;
use crate::speedrun::mastery::Pool;

/// Pre-registered give-up thresholds. Below EITHER of these, readiness returns
/// NoScore. These are code, not a UI hint (PRD 9).
const MIN_GRADED_REVIEWS: u32 = 200;
const MIN_COVERAGE: f64 = 0.50;

impl crate::services::SpeedrunService for Collection {
    /// Trivial read-only health check proving the proto -> Rust -> Python
    /// plumbing works end to end. Performs no writes.
    fn speedrun_ping(&mut self) -> error::Result<SpeedrunPingResponse> {
        let engine_version = crate::version::version().to_string();
        Ok(SpeedrunPingResponse {
            marker: format!("speedrun-ok:{engine_version}"),
            engine_version,
        })
    }

    /// Compute exam readiness. The return type is a oneof, so a bare number can
    /// never be emitted. The give-up rule is enforced here as an assertion:
    /// below the data threshold we return NoScore with the evidence and the
    /// single best next action.
    fn compute_readiness(
        &mut self,
        input: ComputeReadinessRequest,
    ) -> error::Result<ReadinessResult> {
        let graded_reviews = self.graded_review_count()?;
        let unit_weights: HashMap<String, f64> = input
            .units
            .iter()
            .map(|u| (u.unit_id.clone(), u.weight))
            .collect();
        let coverage_pct = self.weighted_coverage(&input.expected_subtopics, &unit_weights)?;

        let reviews_ok = graded_reviews >= MIN_GRADED_REVIEWS;
        let coverage_ok = coverage_pct >= MIN_COVERAGE;

        if !reviews_ok || !coverage_ok {
            return Ok(below_threshold_no_score(graded_reviews, coverage_pct));
        }

        // The data threshold is met, but on the Wednesday core there are no
        // calibrated models yet. Refuse to invent a number (the honesty rule): we
        // still return NoScore, just with a different reason.
        Ok(ReadinessResult {
            value: Some(readiness_result::Value::NoScore(NoScore {
                reason: "Data threshold met, but the readiness score model is not \
                         yet calibrated, so no number is shown."
                    .into(),
                graded_reviews,
                reviews_needed: 0,
                coverage_pct,
                next_best_action: "Keep reviewing across all three units; calibrated \
                                   scoring arrives with the memory and performance \
                                   models."
                    .into(),
            })),
        })
    }

    fn get_mastery_state(&mut self, input: MasteryRequest) -> error::Result<MasteryState> {
        let stats = self.speedrun_subtopic_stats(&input.expected_subtopics)?;
        let pools = compute_pools(&stats);

        // Per-unit rollup, in first-seen order.
        let mut unit_order: Vec<String> = Vec::new();
        let mut unit_total: std::collections::HashMap<String, u32> =
            std::collections::HashMap::new();
        let mut unit_cleared: std::collections::HashMap<String, u32> =
            std::collections::HashMap::new();
        for s in &stats {
            if !unit_total.contains_key(&s.unit_id) {
                unit_order.push(s.unit_id.clone());
            }
            *unit_total.entry(s.unit_id.clone()).or_default() += 1;
            if s.gate_cleared() {
                *unit_cleared.entry(s.unit_id.clone()).or_default() += 1;
            }
        }

        let subtopics = stats
            .iter()
            .map(|s| {
                let tag = s.tag();
                let pool = pools.get(&tag).copied().unwrap_or(Pool::Blocked);
                SubtopicMastery {
                    tag,
                    unit_id: s.unit_id.clone(),
                    subtopic_id: s.subtopic_id.clone(),
                    reviews: s.reviews,
                    correct: s.correct,
                    accuracy: s.accuracy(),
                    mean_retrievability: s.mean_retrievability(),
                    gate_cleared: s.gate_cleared(),
                    pool: pool_to_proto(pool) as i32,
                }
            })
            .collect();

        let units = unit_order
            .into_iter()
            .map(|unit| {
                let total = unit_total.get(&unit).copied().unwrap_or(0);
                let cleared = unit_cleared.get(&unit).copied().unwrap_or(0);
                UnitMastery {
                    unit_id: unit,
                    subtopics_total: total,
                    subtopics_cleared: cleared,
                    mastered: total > 0 && cleared == total,
                }
            })
            .collect();

        Ok(MasteryState { subtopics, units })
    }

    fn get_mastery_ordered_new_cards(
        &mut self,
        input: MasteryRequest,
    ) -> error::Result<MasteryOrderedCards> {
        let stats = self.speedrun_subtopic_stats(&input.expected_subtopics)?;
        let pools = compute_pools(&stats);
        let cards = self.speedrun_new_cards_with_subtopic(&input.expected_subtopics)?;
        let ordered = order_new_cards(&cards, &pools);
        Ok(MasteryOrderedCards {
            card_ids: ordered.into_iter().map(|c| c.0).collect(),
        })
    }
}

fn pool_to_proto(pool: Pool) -> anki_proto::speedrun::MasteryPool {
    match pool {
        Pool::Blocked => anki_proto::speedrun::MasteryPool::Blocked,
        Pool::WithinUnit => anki_proto::speedrun::MasteryPool::WithinUnit,
        Pool::CrossUnit => anki_proto::speedrun::MasteryPool::CrossUnit,
    }
}

impl Collection {
    /// Number of graded reviews (a rating was given) in the revlog.
    fn graded_review_count(&self) -> error::Result<u32> {
        let count: i64 =
            self.storage
                .db
                .query_row("select count() from revlog where ease > 0", [], |row| {
                    row.get(0)
                })?;
        Ok(count.max(0) as u32)
    }

    /// Coverage of the expected syllabus, weighted by unit. Each unit's covered
    /// fraction (subtopics present as a note tag / total subtopics in the unit)
    /// is combined by the given unit weights (the SOA section weights), so
    /// skipping a high-weight section can't read as "covered". With no weights,
    /// units are weighted equally. Returns 0.0 when nothing is expected.
    fn weighted_coverage(
        &self,
        expected: &[String],
        unit_weights: &HashMap<String, f64>,
    ) -> error::Result<f64> {
        if expected.is_empty() {
            return Ok(0.0);
        }
        let tags = self.storage.all_tags_in_notes()?;
        let mut total: HashMap<String, u32> = HashMap::new();
        let mut covered: HashMap<String, u32> = HashMap::new();
        for tag in expected {
            if let Some((unit, _sub)) = parse_subtopic_tag(tag) {
                *total.entry(unit.clone()).or_default() += 1;
                if tags.contains(&UniCase::new(tag.clone())) {
                    *covered.entry(unit).or_default() += 1;
                }
            }
        }
        if total.is_empty() {
            return Ok(0.0);
        }
        let (mut num, mut den) = (0.0, 0.0);
        for (unit, tot) in &total {
            let frac = covered.get(unit).copied().unwrap_or(0) as f64 / *tot as f64;
            let weight = unit_weights.get(unit).copied().unwrap_or(1.0);
            num += weight * frac;
            den += weight;
        }
        Ok(if den > 0.0 { num / den } else { 0.0 })
    }
}

fn below_threshold_no_score(graded_reviews: u32, coverage_pct: f64) -> ReadinessResult {
    let reviews_ok = graded_reviews >= MIN_GRADED_REVIEWS;
    let coverage_ok = coverage_pct >= MIN_COVERAGE;
    let reviews_needed = MIN_GRADED_REVIEWS.saturating_sub(graded_reviews);

    let mut missing = Vec::new();
    if !reviews_ok {
        missing.push(format!(
            "{graded_reviews}/{MIN_GRADED_REVIEWS} graded reviews"
        ));
    }
    if !coverage_ok {
        missing.push(format!(
            "{:.0}% of the required {:.0}% syllabus coverage",
            coverage_pct * 100.0,
            MIN_COVERAGE * 100.0
        ));
    }
    let reason = format!("Not enough data yet: {}.", missing.join(" and "));

    // Coverage gates readiness, so prioritise it as the single best next action.
    let next_best_action = if !coverage_ok {
        "Study more subtopics: reach 50% syllabus coverage before a score is shown.".to_string()
    } else {
        format!("Complete {reviews_needed} more graded reviews to reach 200.")
    };

    ReadinessResult {
        value: Some(readiness_result::Value::NoScore(NoScore {
            reason,
            graded_reviews,
            reviews_needed,
            coverage_pct,
            next_best_action,
        })),
    }
}

#[cfg(test)]
mod tests {
    use anki_proto::speedrun::readiness_result::Value;
    use anki_proto::speedrun::ComputeReadinessRequest;

    use crate::collection::Collection;
    use crate::prelude::*;
    use crate::services::SpeedrunService;
    use crate::tests::NoteAdder;

    #[test]
    fn ping_returns_expected_marker() {
        let mut col = Collection::new();
        let resp = col.speedrun_ping().unwrap();
        assert!(
            resp.marker.starts_with("speedrun-ok:"),
            "unexpected marker: {}",
            resp.marker
        );
    }

    #[test]
    fn ping_marker_embeds_engine_version() {
        let mut col = Collection::new();
        let resp = col.speedrun_ping().unwrap();
        let version = crate::version::version();
        assert_eq!(resp.engine_version, version);
        assert_eq!(resp.marker, format!("speedrun-ok:{version}"));
    }

    #[test]
    fn ping_does_not_modify_collection() {
        // A read-only RPC must not write to the collection, so total_changes()
        // (rows modified since the DB connection opened) must be unchanged.
        let mut col = Collection::new();
        let before = col.changes_since_open().unwrap();
        let resp = col.speedrun_ping().unwrap();
        assert!(resp.marker.starts_with("speedrun-ok:"));
        let after = col.changes_since_open().unwrap();
        assert_eq!(
            before, after,
            "speedrun_ping must not modify the collection"
        );
    }

    fn expected() -> Vec<String> {
        vec![
            "subtopic::general::conditional".to_string(),
            "subtopic::general::bayes".to_string(),
            "subtopic::univariate::binomial".to_string(),
            "subtopic::multivariate::covariance".to_string(),
        ]
    }

    fn request(tags: Vec<String>) -> ComputeReadinessRequest {
        ComputeReadinessRequest {
            expected_subtopics: tags,
            units: Vec::new(),
        }
    }

    fn add_tagged_note(col: &mut Collection, tags: &[&str]) {
        let mut note = NoteAdder::basic(col).note();
        note.tags = tags.iter().map(|s| s.to_string()).collect();
        col.add_note(&mut note, DeckId(1)).unwrap();
    }

    fn insert_graded_reviews(col: &mut Collection, n: usize) {
        let base: i64 = 1_600_000_000_000;
        let rows: Vec<String> = (0..n)
            .map(|i| format!("({},1,-1,3,1,1,2500,1000,1)", base + i as i64))
            .collect();
        let sql = format!(
            "insert into revlog (id,cid,usn,ease,ivl,lastIvl,factor,time,type) values {};",
            rows.join(",")
        );
        col.storage.db.execute_batch(&sql).unwrap();
    }

    #[test]
    fn give_up_on_empty_collection() {
        let mut col = Collection::new();
        let result = col.compute_readiness(request(expected())).unwrap();
        match result.value.unwrap() {
            Value::NoScore(no_score) => {
                assert_eq!(no_score.graded_reviews, 0);
                assert_eq!(no_score.reviews_needed, 200);
                assert_eq!(no_score.coverage_pct, 0.0);
                assert!(!no_score.next_best_action.is_empty());
            }
            Value::Score(_) => panic!("must not return a score below the threshold"),
        }
    }

    #[test]
    fn give_up_when_reviews_below_threshold_even_at_full_coverage() {
        let mut col = Collection::new();
        for tag in expected() {
            add_tagged_note(&mut col, &[tag.as_str()]);
        }
        let result = col.compute_readiness(request(expected())).unwrap();
        match result.value.unwrap() {
            Value::NoScore(no_score) => {
                assert_eq!(no_score.coverage_pct, 1.0);
                assert!(no_score.reviews_needed > 0);
            }
            Value::Score(_) => panic!("must not return a score with < 200 reviews"),
        }
    }

    #[test]
    fn meeting_thresholds_still_refuses_a_number_without_models() {
        let mut col = Collection::new();
        for tag in expected() {
            add_tagged_note(&mut col, &[tag.as_str()]); // 100% coverage
        }
        insert_graded_reviews(&mut col, 200); // >= 200 graded reviews
        let result = col.compute_readiness(request(expected())).unwrap();
        match result.value.unwrap() {
            Value::NoScore(no_score) => {
                assert_eq!(no_score.reviews_needed, 0);
                assert!(
                    no_score.reason.to_lowercase().contains("calibrat"),
                    "unexpected reason: {}",
                    no_score.reason
                );
            }
            Value::Score(_) => {
                panic!("Wednesday has no calibrated model; must not emit a number")
            }
        }
    }

    #[test]
    fn coverage_is_weighted_by_unit_weights() {
        let mut col = Collection::new();
        // Two units, one subtopic each; cover only the heavy unit "b".
        add_tagged_note(&mut col, &["subtopic::b::y"]);
        let req = ComputeReadinessRequest {
            expected_subtopics: vec!["subtopic::a::x".to_string(), "subtopic::b::y".to_string()],
            units: vec![
                anki_proto::speedrun::UnitWeight {
                    unit_id: "a".into(),
                    weight: 1.0,
                },
                anki_proto::speedrun::UnitWeight {
                    unit_id: "b".into(),
                    weight: 9.0,
                },
            ],
        };
        match col.compute_readiness(req).unwrap().value.unwrap() {
            Value::NoScore(no_score) => {
                // Heavy unit b (weight 9 of 10) is covered -> ~0.9, not 0.5.
                assert!(
                    (no_score.coverage_pct - 0.9).abs() < 1e-9,
                    "coverage={}",
                    no_score.coverage_pct
                );
            }
            Value::Score(_) => panic!("must not score below threshold"),
        }
    }
}
