// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

use anki_proto::speedrun::readiness_result;
use anki_proto::speedrun::ComputeReadinessRequest;
use anki_proto::speedrun::NoScore;
use anki_proto::speedrun::ReadinessResult;
use anki_proto::speedrun::SpeedrunPingResponse;
use unicase::UniCase;

use crate::collection::Collection;
use crate::error;

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
    /// never be emitted. The give-up rule is enforced here as an assertion: below
    /// the data threshold we return NoScore with the evidence and the single best
    /// next action.
    fn compute_readiness(
        &mut self,
        input: ComputeReadinessRequest,
    ) -> error::Result<ReadinessResult> {
        let graded_reviews = self.graded_review_count()?;
        let coverage_pct = self.subtopic_coverage(&input.expected_subtopics)?;

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
}

impl Collection {
    /// Number of graded reviews (a rating was given) in the revlog.
    fn graded_review_count(&self) -> error::Result<u32> {
        let count: i64 = self.storage.db.query_row(
            "select count() from revlog where ease > 0",
            [],
            |row| row.get(0),
        )?;
        Ok(count.max(0) as u32)
    }

    /// Fraction of the expected syllabus subtopics that appear as a tag on at
    /// least one note. Returns 0.0 when no subtopics are expected.
    fn subtopic_coverage(&self, expected: &[String]) -> error::Result<f64> {
        if expected.is_empty() {
            return Ok(0.0);
        }
        let tags = self.storage.all_tags_in_notes()?;
        let covered = expected
            .iter()
            .filter(|tag| tags.contains(&UniCase::new((*tag).clone())))
            .count();
        Ok(covered as f64 / expected.len() as f64)
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
        "Study more subtopics: reach 50% syllabus coverage before a score is shown."
            .to_string()
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
        assert_eq!(before, after, "speedrun_ping must not modify the collection");
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
}
