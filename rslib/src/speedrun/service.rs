// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

use std::collections::HashMap;

use anki_proto::decks::DeckTreeNode;
use anki_proto::speedrun::readiness_result;
use anki_proto::speedrun::ComputeReadinessRequest;
use anki_proto::speedrun::MasteryOrderedCards;
use anki_proto::speedrun::MasteryOverall;
use anki_proto::speedrun::MasteryRequest;
use anki_proto::speedrun::MasteryState;
use anki_proto::speedrun::NoScore;
use anki_proto::speedrun::PointsAtStakeCard;
use anki_proto::speedrun::PointsAtStakeOrder;
use anki_proto::speedrun::ReadinessResult;
use anki_proto::speedrun::SpeedrunPingResponse;
use anki_proto::speedrun::StudyPace;
use anki_proto::speedrun::StudyPlan;
use anki_proto::speedrun::StudyPlanItem;
use anki_proto::speedrun::StudyPriority;
use anki_proto::speedrun::StudyRecommendation;
use anki_proto::speedrun::SubtopicMastery;
use anki_proto::speedrun::UnitMastery;

use crate::collection::Collection;
use crate::error;
use crate::speedrun::mastery::build_study_plan;
use crate::speedrun::mastery::compute_pace;
use crate::speedrun::mastery::compute_pools;
use crate::speedrun::mastery::order_new_cards;
use crate::speedrun::mastery::parse_subtopic_tag;
use crate::speedrun::mastery::points_at_stake_order;
use crate::speedrun::mastery::recommend_study;
use crate::speedrun::mastery::study_priorities;
use crate::speedrun::mastery::subtopic_weakness;
use crate::speedrun::mastery::weighted_mastery;
use crate::speedrun::mastery::Pool;
use crate::speedrun::mastery::EXAM_DATE_KEY;
use crate::timestamp::TimestampSecs;

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
        let mut stats = self.speedrun_subtopic_stats(&input.expected_subtopics)?;

        // Attach each subtopic's importance weight from the request (the
        // editable topic-map emphasis). Absent weights stay 0, which makes the
        // weighted rollup fall back to a plain count fraction.
        let sub_weights: HashMap<String, f64> = input
            .subtopic_weights
            .iter()
            .map(|w| (w.tag.clone(), w.weight))
            .collect();
        for s in &mut stats {
            s.weight = sub_weights.get(&s.tag()).copied().unwrap_or(0.0);
        }
        let unit_req_weights: HashMap<String, f64> = input
            .units
            .iter()
            .map(|u| (u.unit_id.clone(), u.weight))
            .collect();
        let weighted = weighted_mastery(&stats);

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
                    weight: s.weight,
                }
            })
            .collect();

        let units: Vec<UnitMastery> = unit_order
            .into_iter()
            .map(|unit| {
                let total = unit_total.get(&unit).copied().unwrap_or(0);
                let cleared = unit_cleared.get(&unit).copied().unwrap_or(0);
                // Prefer the summed subtopic weight; fall back to the unit's own
                // section weight when subtopic weights weren't supplied.
                let summed = weighted.per_unit_weight.get(&unit).copied().unwrap_or(0.0);
                let weight = if summed > 0.0 {
                    summed
                } else {
                    unit_req_weights.get(&unit).copied().unwrap_or(0.0)
                };
                let weighted_mastery_pct = weighted.per_unit_pct.get(&unit).copied().unwrap_or(0.0);
                UnitMastery {
                    unit_id: unit,
                    subtopics_total: total,
                    subtopics_cleared: cleared,
                    mastered: total > 0 && cleared == total,
                    weight,
                    weighted_mastery_pct,
                }
            })
            .collect();

        // Honest overall rollup, computed in the engine from the same gate as the
        // scheduler. Measured counts only (demonstrated mastery), never a score.
        let o = crate::speedrun::mastery::mastery_overall(&stats);
        let overall = Some(MasteryOverall {
            subtopics_total: o.subtopics_total,
            subtopics_mastered: o.subtopics_mastered,
            subtopics_in_progress: o.subtopics_in_progress,
            subtopics_not_started: o.subtopics_not_started,
            units_total: o.units_total,
            units_mastered: o.units_mastered,
            total_reviews: o.total_reviews,
            weighted_mastery_pct: weighted.overall_pct,
        });

        // "What to study next", ranked by importance weight x measured
        // opportunity. Cleared subtopics drop out; this only reorders measured
        // state, so it never fabricates a score.
        let priorities = study_priorities(&stats)
            .into_iter()
            .map(|p| StudyPriority {
                tag: p.tag,
                unit_id: p.unit_id,
                subtopic_id: p.subtopic_id,
                weight: p.weight,
                priority_score: p.score,
                reason: p.reason,
            })
            .collect();

        // Tier-aware "what to study next": block the weakest uncleared subtopic,
        // then interleave a unit once it has >= 2 cleared, then cross-unit.
        let rec = recommend_study(&stats);
        let recommendation = Some(StudyRecommendation {
            mode: study_mode_to_proto(rec.mode) as i32,
            subtopic_tag: rec.subtopic_tag.unwrap_or_default(),
            unit_id: rec.unit_id.unwrap_or_default(),
        });

        Ok(MasteryState {
            subtopics,
            units,
            overall,
            priorities,
            recommendation,
        })
    }

    fn get_mastery_ordered_new_cards(
        &mut self,
        input: MasteryRequest,
    ) -> error::Result<MasteryOrderedCards> {
        let stats = self.speedrun_subtopic_stats(&input.expected_subtopics)?;
        let pools = compute_pools(&stats);
        let cards = self.speedrun_new_cards_with_subtopic(&input.expected_subtopics)?;
        // The RPC reports the full three-tier order; the ablated variant is a
        // live-queue-only experiment flag (see speedrun_reorder_new_cards).
        let ordered = order_new_cards(&cards, &pools, false);
        Ok(MasteryOrderedCards {
            card_ids: ordered.into_iter().map(|c| c.0).collect(),
        })
    }

    /// Points-at-stake review order: due cards sorted by topic importance
    /// weight times measured student weakness, highest-value first.
    /// Weakness comes from real reviews (1 - mean retrievability), so
    /// nothing here is fabricated; this is a read-only ordering that never
    /// reschedules a card.
    fn get_points_at_stake_order(
        &mut self,
        input: MasteryRequest,
    ) -> error::Result<PointsAtStakeOrder> {
        let stats = self.speedrun_subtopic_stats(&input.expected_subtopics)?;
        let weights: HashMap<String, f64> = input
            .subtopic_weights
            .iter()
            .map(|w| (w.tag.clone(), w.weight))
            .collect();
        let weakness: HashMap<String, f64> = stats
            .iter()
            .map(|s| (s.tag(), subtopic_weakness(s)))
            .collect();
        let cards = self.speedrun_due_cards_with_subtopic(&input.expected_subtopics)?;
        let ordered = points_at_stake_order(&cards, &weights, &weakness);
        Ok(PointsAtStakeOrder {
            cards: ordered
                .into_iter()
                .map(|c| PointsAtStakeCard {
                    card_id: c.card_id.0,
                    tag: c.tag,
                    weight: c.weight,
                    weakness: c.weakness,
                    stakes: c.stakes,
                })
                .collect(),
        })
    }

    /// Today's tiered study plan. Sorts each subtopic/unit into a tier from the
    /// measured gate state (blocked -> within-unit -> cross-unit), then
    /// attaches Anki's own deck-tree counts for today (daily-limit capped,
    /// the same numbers the deck list shows) to the matching deck. Only
    /// decks with something due today are returned. Read-only reporting —
    /// it never reschedules or fabricates a score; the tiering itself is
    /// the pure, unit-tested `build_study_plan`.
    fn get_study_plan(&mut self, input: MasteryRequest) -> error::Result<StudyPlan> {
        let mut stats = self.speedrun_subtopic_stats(&input.expected_subtopics)?;
        let sub_weights: HashMap<String, f64> = input
            .subtopic_weights
            .iter()
            .map(|w| (w.tag.clone(), w.weight))
            .collect();
        for s in &mut stats {
            s.weight = sub_weights.get(&s.tag()).copied().unwrap_or(0.0);
        }
        let pools = compute_pools(&stats);

        // Which deck holds each subtopic's cards (so we can read its counts).
        let tag_deck = self.speedrun_subtopic_deck_ids(&input.expected_subtopics)?;

        // Today's due counts from Anki's own deck tree (daily-limit capped), plus
        // the tree's parent links so we can walk subtopic -> unit -> root deck.
        let tree = self.deck_tree(Some(TimestampSecs::now()))?;
        let mut counts: HashMap<i64, (u32, u32, u32, u32)> = HashMap::new();
        let mut parent: HashMap<i64, i64> = HashMap::new();
        collect_tree(&tree, 0, &mut counts, &mut parent);
        let name_by_id: HashMap<i64, String> = self
            .storage
            .get_all_deck_names()?
            .into_iter()
            .map(|(id, name)| (id.0, name))
            .collect();

        let items = build_study_plan(&stats, &pools, &tag_deck, &counts, &parent)
            .into_iter()
            .map(|p| StudyPlanItem {
                tier: study_mode_to_proto(p.tier) as i32,
                deck_id: p.deck_id,
                deck_name: name_by_id.get(&p.deck_id).cloned().unwrap_or_default(),
                subtopic_tag: p.subtopic_tag.unwrap_or_default(),
                unit_id: p.unit_id.unwrap_or_default(),
                new_count: p.new,
                review_count: p.review,
                learn_count: p.learn,
                total_including_children: p.total,
            })
            .collect();
        Ok(StudyPlan { items })
    }

    /// Coverage pace vs the user's exam date. Counts the new (unstudied)
    /// syllabus cards, reads the exam deck's new-cards/day limit, and works out
    /// the pace needed to introduce them all before the exam. Pure arithmetic
    /// over measured counts (see `compute_pace`); it is a coverage pace, never
    /// the readiness score. Read-only.
    fn get_study_pace(&mut self, input: MasteryRequest) -> error::Result<StudyPace> {
        let exam_ts = self.get_config_optional::<i64, _>(EXAM_DATE_KEY);
        let has_exam_date = exam_ts.is_some();
        let exam_timestamp = exam_ts.unwrap_or(0);
        let remaining_new = self
            .speedrun_new_cards_with_subtopic(&input.expected_subtopics)?
            .len() as u32;
        let current_new_per_day = self
            .speedrun_root_new_per_day(&input.expected_subtopics)?
            .unwrap_or(0);
        let now = TimestampSecs::now().0;
        let days_left = if has_exam_date {
            ((exam_timestamp - now) as f64 / 86_400.0).round() as i64
        } else {
            0
        };
        let pace = compute_pace(remaining_new, current_new_per_day, days_left, has_exam_date);
        Ok(StudyPace {
            has_exam_date,
            exam_timestamp,
            days_left,
            remaining_new,
            current_new_per_day,
            recommended_new_per_day: pace.recommended_new_per_day,
            projected_days_to_finish: pace.projected_days_to_finish,
            on_track: pace.on_track,
        })
    }
}

/// Flatten a deck tree into per-deck counts `(new, review, learn, total)` and a
/// child -> parent map. The top node has deck id 0, so a level-1 deck's parent
/// is 0.
fn collect_tree(
    node: &DeckTreeNode,
    parent_id: i64,
    counts: &mut HashMap<i64, (u32, u32, u32, u32)>,
    parent: &mut HashMap<i64, i64>,
) {
    counts.insert(
        node.deck_id,
        (
            node.new_count,
            node.review_count,
            node.learn_count,
            node.total_including_children,
        ),
    );
    parent.insert(node.deck_id, parent_id);
    for child in &node.children {
        collect_tree(child, node.deck_id, counts, parent);
    }
}

fn pool_to_proto(pool: Pool) -> anki_proto::speedrun::MasteryPool {
    match pool {
        Pool::Blocked => anki_proto::speedrun::MasteryPool::Blocked,
        Pool::WithinUnit => anki_proto::speedrun::MasteryPool::WithinUnit,
        Pool::CrossUnit => anki_proto::speedrun::MasteryPool::CrossUnit,
    }
}

fn study_mode_to_proto(
    mode: crate::speedrun::mastery::StudyMode,
) -> anki_proto::speedrun::StudyMode {
    use crate::speedrun::mastery::StudyMode as M;
    match mode {
        M::Blocked => anki_proto::speedrun::StudyMode::Blocked,
        M::WithinUnit => anki_proto::speedrun::StudyMode::WithinUnit,
        M::CrossUnit => anki_proto::speedrun::StudyMode::CrossUnit,
        M::AllMastered => anki_proto::speedrun::StudyMode::AllMastered,
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

    /// Practiced coverage of the expected syllabus, weighted by unit. Per PRD
    /// 9, "coverage = % of syllabus practiced": a subtopic counts only once
    /// it has at least one graded review. Merely owning a card you have
    /// never studied does NOT count, so a freshly imported full deck reads
    /// 0%, not 100%. Each unit's practiced fraction is combined by the
    /// given unit weights (the SOA section weights), so skipping a
    /// high-weight section can't read as "covered". With no weights, units
    /// are weighted equally. Returns 0.0 when nothing is expected.
    fn weighted_coverage(
        &self,
        expected: &[String],
        unit_weights: &HashMap<String, f64>,
    ) -> error::Result<f64> {
        if expected.is_empty() {
            return Ok(0.0);
        }
        let practiced = self.practiced_subtopics()?;
        let mut total: HashMap<String, u32> = HashMap::new();
        let mut covered: HashMap<String, u32> = HashMap::new();
        for tag in expected {
            if let Some((unit, _sub)) = parse_subtopic_tag(tag) {
                *total.entry(unit.clone()).or_default() += 1;
                if practiced.contains(&tag.to_ascii_lowercase()) {
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

    /// Subtopic tags (lowercased) with at least one graded review on some card.
    /// This is the "practiced" set behind coverage: it separates a syllabus you
    /// have actually studied from one you merely own cards for.
    fn practiced_subtopics(&self) -> error::Result<std::collections::HashSet<String>> {
        let sql = "
            SELECT DISTINCT n.tags
            FROM cards c JOIN notes n ON c.nid = n.id
            WHERE n.tags LIKE '% subtopic::%'
              AND EXISTS (SELECT 1 FROM revlog r WHERE r.cid = c.id AND r.ease > 0)";
        let mut stmt = self.storage.db.prepare_cached(sql)?;
        let mut rows = stmt.query([])?;
        let mut out = std::collections::HashSet::new();
        while let Some(row) = rows.next()? {
            let tags: String = row.get(0)?;
            for t in tags.split_whitespace() {
                if t.starts_with("subtopic::") {
                    out.insert(t.to_ascii_lowercase());
                }
            }
        }
        Ok(out)
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
    use anki_proto::speedrun::MasteryRequest;

    use crate::collection::Collection;
    use crate::deckconfig::DeckConfigId;
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

    /// Add a tagged note and give its card `reviews` graded reviews, so the
    /// subtopic counts as practiced. Reviews land on the real card id, which is
    /// what practiced-coverage requires (an unstudied card must not count).
    fn add_reviewed_note(col: &mut Collection, tags: &[&str], reviews: usize) {
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
        if reviews == 0 {
            return;
        }
        // Space revlog ids per note so primary keys never collide.
        let base: i64 = 1_600_000_000_000 + note.id.0 * 1_000_000;
        let rows: Vec<String> = (0..reviews)
            .map(|i| format!("({},{},-1,3,1,1,2500,1000,1)", base + i as i64, cid))
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
    fn unstudied_cards_do_not_count_as_coverage() {
        // Regression for the "100% before I've done anything" bug: owning a full
        // deck you have never studied must read 0% coverage. Coverage is
        // "% of syllabus practiced", not "cards owned".
        let mut col = Collection::new();
        for tag in expected() {
            add_tagged_note(&mut col, &[tag.as_str()]); // cards exist, zero
                                                        // reviews
        }
        match col
            .compute_readiness(request(expected()))
            .unwrap()
            .value
            .unwrap()
        {
            Value::NoScore(no_score) => {
                assert_eq!(no_score.coverage_pct, 0.0);
                assert_eq!(no_score.graded_reviews, 0);
            }
            Value::Score(_) => panic!("must not score an unstudied deck"),
        }
    }

    #[test]
    fn give_up_when_reviews_below_threshold_even_at_full_coverage() {
        let mut col = Collection::new();
        for tag in expected() {
            add_reviewed_note(&mut col, &[tag.as_str()], 1); // practiced, but
                                                             // tiny
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
        // 50 reviews on each of the 4 subtopics: 200 graded reviews AND full
        // practiced coverage, so both give-up gates are met.
        for tag in expected() {
            add_reviewed_note(&mut col, &[tag.as_str()], 50);
        }
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
        // Two units, one subtopic each; practise only the heavy unit "b".
        add_reviewed_note(&mut col, &["subtopic::b::y"], 1);
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

    fn add_tagged_note_in_deck(col: &mut Collection, tags: &[&str], deck: DeckId) {
        let mut note = NoteAdder::basic(col).note();
        note.tags = tags.iter().map(|s| s.to_string()).collect();
        col.add_note(&mut note, deck).unwrap();
    }

    #[test]
    fn study_plan_reads_real_deck_counts_for_blocked_subtopics() {
        // End-to-end: the plan attributes Anki's own deck-tree counts to the
        // right subtopic decks. All cards are new, so both subtopics are blocked
        // and each subtopic deck shows its new card as due today.
        let mut col = Collection::new();
        let _root = col.get_or_create_normal_deck("SOA Exam P").unwrap();
        let _unit = col
            .get_or_create_normal_deck("SOA Exam P::General Probability")
            .unwrap();
        let a = col
            .get_or_create_normal_deck("SOA Exam P::General Probability::A")
            .unwrap();
        let b = col
            .get_or_create_normal_deck("SOA Exam P::General Probability::B")
            .unwrap();
        add_tagged_note_in_deck(&mut col, &["subtopic::general::a"], a.id);
        add_tagged_note_in_deck(&mut col, &["subtopic::general::b"], b.id);

        let plan = col
            .get_study_plan(MasteryRequest {
                expected_subtopics: vec![
                    "subtopic::general::a".to_string(),
                    "subtopic::general::b".to_string(),
                ],
                units: vec![],
                subtopic_weights: vec![],
            })
            .unwrap();

        assert_eq!(plan.items.len(), 2, "two blocked subtopic decks due today");
        for it in &plan.items {
            assert_eq!(
                it.tier,
                anki_proto::speedrun::StudyMode::Blocked as i32,
                "all-new cards are blocked practice"
            );
            assert!(it.new_count >= 1, "each subtopic deck has a new card due");
            assert!(
                it.deck_name
                    .starts_with("SOA Exam P::General Probability::"),
                "points at the subtopic deck: {}",
                it.deck_name
            );
        }
        let ids: std::collections::HashSet<i64> = plan.items.iter().map(|i| i.deck_id).collect();
        assert!(ids.contains(&a.id.0) && ids.contains(&b.id.0));
    }

    #[test]
    fn study_plan_empty_when_nothing_due() {
        // No cards anywhere -> nothing is actionable -> the honest empty plan.
        let mut col = Collection::new();
        let plan = col
            .get_study_plan(MasteryRequest {
                expected_subtopics: vec!["subtopic::general::a".to_string()],
                units: vec![],
                subtopic_weights: vec![],
            })
            .unwrap();
        assert!(plan.items.is_empty());
    }

    fn pace_req() -> MasteryRequest {
        MasteryRequest {
            expected_subtopics: vec![
                "subtopic::general::a".to_string(),
                "subtopic::general::b".to_string(),
            ],
            units: vec![],
            subtopic_weights: vec![],
        }
    }

    fn seed_two_new_cards(col: &mut Collection) {
        col.get_or_create_normal_deck("SOA Exam P").unwrap();
        col.get_or_create_normal_deck("SOA Exam P::General Probability")
            .unwrap();
        let a = col
            .get_or_create_normal_deck("SOA Exam P::General Probability::A")
            .unwrap();
        let b = col
            .get_or_create_normal_deck("SOA Exam P::General Probability::B")
            .unwrap();
        add_tagged_note_in_deck(col, &["subtopic::general::a"], a.id);
        add_tagged_note_in_deck(col, &["subtopic::general::b"], b.id);
    }

    #[test]
    fn study_pace_without_exam_date_reports_counts_but_no_track() {
        // Two new cards, default 20/day, no exam date: we report the measured
        // counts but never claim on/off track without a deadline.
        let mut col = Collection::new();
        seed_two_new_cards(&mut col);
        let pace = col.get_study_pace(pace_req()).unwrap();
        assert!(!pace.has_exam_date);
        assert_eq!(pace.remaining_new, 2);
        assert_eq!(pace.current_new_per_day, 20); // default deck preset
        assert!(!pace.on_track);
    }

    #[test]
    fn study_pace_with_distant_exam_is_on_track() {
        let mut col = Collection::new();
        seed_two_new_cards(&mut col);
        let now = crate::timestamp::TimestampSecs::now().0;
        col.set_config_json("speedrunExamDate", &(now + 100 * 86_400), false)
            .unwrap();
        let pace = col.get_study_pace(pace_req()).unwrap();
        assert!(pace.has_exam_date);
        assert!(pace.days_left >= 99 && pace.days_left <= 100);
        // 2 new at 20/day finishes in 1 day, well before 100 -> on track.
        assert_eq!(pace.projected_days_to_finish, 1);
        assert!(pace.on_track);
    }

    #[test]
    fn study_pace_with_imminent_exam_and_many_cards_is_behind() {
        let mut col = Collection::new();
        // Root deck with a tiny daily limit + more cards than can fit in 1 day.
        col.get_or_create_normal_deck("SOA Exam P").unwrap();
        col.get_or_create_normal_deck("SOA Exam P::General Probability")
            .unwrap();
        let a = col
            .get_or_create_normal_deck("SOA Exam P::General Probability::A")
            .unwrap();
        // Shrink the exam deck's new/day to 1 so two new cards can't fit in a day.
        let mut conf = col
            .get_deck_config(DeckConfigId(1), false)
            .unwrap()
            .unwrap();
        conf.inner.new_per_day = 1;
        col.add_or_update_deck_config(&mut conf).unwrap();
        add_tagged_note_in_deck(&mut col, &["subtopic::general::a"], a.id);
        add_tagged_note_in_deck(&mut col, &["subtopic::general::b"], a.id);

        let now = crate::timestamp::TimestampSecs::now().0;
        col.set_config_json("speedrunExamDate", &(now + 86_400), false)
            .unwrap(); // exam ~tomorrow
        let pace = col.get_study_pace(pace_req()).unwrap();
        assert_eq!(pace.current_new_per_day, 1);
        assert_eq!(pace.remaining_new, 2);
        assert!(!pace.on_track); // 2 cards at 1/day can't finish by tomorrow
        assert!(pace.recommended_new_per_day >= 2);
    }
}
