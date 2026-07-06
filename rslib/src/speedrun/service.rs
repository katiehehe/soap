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
use anki_proto::speedrun::MemoryRecall;
use anki_proto::speedrun::NoScore;
use anki_proto::speedrun::PointsAtStakeCard;
use anki_proto::speedrun::PointsAtStakeOrder;
use anki_proto::speedrun::ReadinessResult;
use anki_proto::speedrun::ReadinessScore;
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
use crate::speedrun::mastery::compute_locks;
use crate::speedrun::mastery::compute_mastery_pace;
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
/// A readiness NUMBER is additionally withheld until there is graded
/// practice-test evidence: at least this many practice-test questions. Below it
/// the model has nothing to estimate P(pass) from, so we still return NoScore.
const MIN_PRACTICE_QUESTIONS: u32 = 30;
/// Documented pass mapping: SOA P is scored 0-10, pass >= 6. Under the simplest
/// linear map (scaled ~= 10 x proportion-correct) that is proportion >= 0.6.
/// Stated in docs/score-models.md so it can be recalibrated with real scaled
/// scores; it is a fixed assumption, never tuned to flatter a result.
const PASS_PROPORTION: f64 = 0.60;
/// Config key holding accumulated practice-test evidence (written by Python's
/// practice_test.record_test). Mirrors PRACTICE_STATS_KEY in that module.
const PRACTICE_STATS_KEY: &str = "speedrunPracticeStats";

/// Accumulated practice-test evidence, read from collection config.
///
/// `questions`/`correct`/`tests` are the RAW integer counts (the give-up gate
/// uses `questions`). `weighted_*` are the same evidence scaled by each test's
/// representativeness (`practice_test.readiness_weight`: a full, whole-exam official
/// test counts 1.0; narrower scope or generated sources count for less). The
/// readiness BAND uses the weighted proportion; they default to 0 for tests
/// recorded before weighting existed, in which case the band falls back to the
/// raw counts.
#[derive(serde::Deserialize, Default)]
struct PracticeStats {
    #[serde(default)]
    questions: u32,
    #[serde(default)]
    correct: u32,
    #[serde(default)]
    tests: u32,
    #[serde(default)]
    weighted_questions: f64,
    #[serde(default)]
    weighted_correct: f64,
}

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

        // The Memory signal (with a range) is computed INDEPENDENTLY of the
        // readiness give-up rule: memory can be shown as soon as there are
        // reviews, even while readiness abstains. It is attached to every return
        // path below.
        let stats = self.speedrun_subtopic_stats(&input.expected_subtopics)?;
        let memory_recall = Some(memory_recall_proto(
            &crate::speedrun::mastery::memory_recall(&stats),
        ));

        let reviews_ok = graded_reviews >= MIN_GRADED_REVIEWS;
        let coverage_ok = coverage_pct >= MIN_COVERAGE;

        let mut result = if !reviews_ok || !coverage_ok {
            below_threshold_no_score(graded_reviews, coverage_pct)
        } else {
            // Review + coverage gates are met. A readiness NUMBER additionally
            // needs graded practice-test evidence (P(pass) is estimated from real
            // graded exam-style results, never invented). Below the
            // practice-question threshold we still return NoScore. That is the
            // honesty rule, not a UI hint.
            let practice: PracticeStats = self.get_config_default(PRACTICE_STATS_KEY);
            if practice.questions < MIN_PRACTICE_QUESTIONS {
                no_practice_evidence_no_score(graded_reviews, coverage_pct, practice.questions)
            } else {
                // Enough graded practice-test evidence: emit the readiness band.
                // Every field is populated (the honesty bundle), so a bare number
                // can't ship. The band uses REPRESENTATIVENESS-WEIGHTED evidence
                // (a full official exam counts most); it falls back to the raw
                // counts for tests recorded before weighting existed. The give-up
                // gate above always used the RAW question count.
                let weighted = practice.weighted_questions > 0.0;
                let (band_q, band_c) = if weighted {
                    (practice.weighted_questions, practice.weighted_correct)
                } else {
                    (practice.questions as f64, practice.correct as f64)
                };
                let band = readiness_from_practice(band_q, band_c, coverage_pct);
                let pct = 100.0 * practice.correct as f64 / practice.questions as f64;
                let mut reasons = vec![
                    format!(
                        "{} graded practice-test questions across {} test(s), {pct:.0}% correct.",
                        practice.questions, practice.tests
                    ),
                    format!("{:.0}% weighted syllabus coverage.", coverage_pct * 100.0),
                    "Projected 0-10 assumes scaled score ~= 10 x proportion correct (see \
                     docs/score-models.md); range is a 95% Wilson interval."
                        .to_string(),
                ];
                if weighted {
                    reasons.insert(
                        1,
                        "Each test is weighted by how representative it is: a full, whole-exam \
                         official test counts most."
                            .to_string(),
                    );
                }
                ReadinessResult {
                    value: Some(readiness_result::Value::Score(ReadinessScore {
                        point: band.point,
                        low: band.low,
                        high: band.high,
                        coverage_pct,
                        confidence: band.confidence,
                        updated_at: TimestampSecs::now().0,
                        reasons,
                        next_best_action: self.readiness_next_action(&input.expected_subtopics)?,
                        // No history of past predictions vs outcomes yet, so past
                        // accuracy is not-yet-available (the UI shows it as such).
                        past_accuracy: 0.0,
                        pass_probability: band.pass_probability,
                    })),
                    memory_recall: None,
                }
            }
        };
        result.memory_recall = memory_recall;
        Ok(result)
    }

    fn get_mastery_state(&mut self, input: MasteryRequest) -> error::Result<MasteryState> {
        let mut stats = self.speedrun_subtopic_stats(&input.expected_subtopics)?;

        // Attach each subtopic's importance weight (editable topic-map emphasis;
        // absent weights stay 0, so the weighted rollup falls back to a plain
        // count) AND its practice-test PERFORMANCE from config. Performance is a
        // SEPARATE signal (shown with its own range) that is AND-ed with the
        // memory gate to decide FULL mastery, but never averaged into it.
        let sub_weights: HashMap<String, f64> = input
            .subtopic_weights
            .iter()
            .map(|w| (w.tag.clone(), w.weight))
            .collect();
        let perf = self.speedrun_performance_config();
        for s in &mut stats {
            s.weight = sub_weights.get(&s.tag()).copied().unwrap_or(0.0);
            s.performance = perf.get(&s.tag()).copied().unwrap_or_default();
        }
        let unit_req_weights: HashMap<String, f64> = input
            .units
            .iter()
            .map(|u| (u.unit_id.clone(), u.weight))
            .collect();
        let weighted = weighted_mastery(&stats);

        let pools = compute_pools(&stats);

        // Guided-learning gate. The DAG comes from the request (the Python topic
        // map); the guided flag and per-topic unlocks come from config.
        // Performance (attached to the stats above) stays a SEPARATE signal: it
        // is OR-ed in to satisfy prerequisites and AND-ed with the memory gate
        // for FULL mastery, but never averaged into a blended score.
        let subtopic_prereqs: HashMap<String, Vec<String>> = input
            .subtopic_prereqs
            .iter()
            .map(|p| (p.tag.clone(), p.prereqs.clone()))
            .collect();
        let unit_prereqs: HashMap<String, Vec<String>> = input
            .unit_prereqs
            .iter()
            .map(|p| (p.unit_id.clone(), p.prereqs.clone()))
            .collect();
        let unlocked = self.speedrun_unlocked_subtopics_config();
        let guided = self.speedrun_guided_mode_enabled();
        let locks = compute_locks(
            &stats,
            &perf,
            &subtopic_prereqs,
            &unit_prereqs,
            &unlocked,
            guided,
        );
        let locked_tags: std::collections::HashSet<String> = locks
            .iter()
            .filter(|(_, v)| v.locked)
            .map(|(k, _)| k.clone())
            .collect();

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
            if s.fully_mastered() {
                *unit_cleared.entry(s.unit_id.clone()).or_default() += 1;
            }
        }

        let subtopics = stats
            .iter()
            .map(|s| {
                let tag = s.tag();
                let pool = pools.get(&tag).copied().unwrap_or(Pool::Blocked);
                // Practice-test performance (separate signal) + guided lock.
                let p = perf.get(&tag).copied().unwrap_or_default();
                let lock = locks.get(&tag).cloned().unwrap_or_default();
                let (recall_low, recall_high) = s.recall_band();
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
                    perf_questions: p.questions,
                    perf_correct: p.correct,
                    perf_accuracy: p.accuracy(),
                    performance_mastered: p.mastered(),
                    locked: lock.locked,
                    unmet_prereqs: lock.unmet_prereqs,
                    recall_low,
                    recall_high,
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
        // opportunity. Cleared subtopics drop out; guided-locked subtopics are
        // withheld too, so the guidance matches what the queue actually serves.
        // This only reorders/filters measured state, so it never fabricates a
        // score.
        let priorities: Vec<StudyPriority> = study_priorities(&stats)
            .into_iter()
            .filter(|p| !locked_tags.contains(&p.tag))
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
        // then interleave a unit once it has >= 2 cleared, then cross-unit. If
        // the guided gate hides the recommended blocked subtopic, point at the
        // highest-priority UNLOCKED subtopic instead.
        let rec = recommend_study(&stats);
        let mut subtopic_tag = rec.subtopic_tag.unwrap_or_default();
        if !subtopic_tag.is_empty() && locked_tags.contains(&subtopic_tag) {
            if let Some(first) = priorities.first() {
                subtopic_tag = first.tag.clone();
            }
        }
        let recommendation = Some(StudyRecommendation {
            mode: study_mode_to_proto(rec.mode) as i32,
            subtopic_tag,
            unit_id: rec.unit_id.unwrap_or_default(),
        });

        Ok(MasteryState {
            subtopics,
            units,
            overall,
            priorities,
            recommendation,
            guided_mode: guided,
            mastery_scheduler_on: self.speedrun_mastery_scheduler_enabled(),
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
    /// decks with something due today are returned. Read-only reporting: it
    /// never reschedules or fabricates a score; the tiering itself is
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

        // Guided gate: drop blocked subtopics whose NEW cards are withheld, so
        // the plan matches what the queue actually serves. Within/cross-unit
        // items carry no subtopic tag, so they pass through untouched.
        let subtopic_prereqs: HashMap<String, Vec<String>> = input
            .subtopic_prereqs
            .iter()
            .map(|p| (p.tag.clone(), p.prereqs.clone()))
            .collect();
        let unit_prereqs: HashMap<String, Vec<String>> = input
            .unit_prereqs
            .iter()
            .map(|p| (p.unit_id.clone(), p.prereqs.clone()))
            .collect();
        let perf = self.speedrun_performance_config();
        let unlocked = self.speedrun_unlocked_subtopics_config();
        let guided = self.speedrun_guided_mode_enabled();
        let locked_tags: std::collections::HashSet<String> = compute_locks(
            &stats,
            &perf,
            &subtopic_prereqs,
            &unit_prereqs,
            &unlocked,
            guided,
        )
        .into_iter()
        .filter(|(_, v)| v.locked)
        .map(|(k, _)| k)
        .collect();

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
            .filter(|p| match &p.subtopic_tag {
                Some(t) => !locked_tags.contains(t),
                None => true,
            })
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

    /// Mastery pace vs the user's exam date. Counts the syllabus subtopics whose
    /// mastery gate is cleared (the SAME gate the map and Overall-mastery use),
    /// measures the study history from the first graded review, and works out
    /// whether the observed clear-rate masters the rest before the exam. Pure
    /// arithmetic over measured counts (see `compute_mastery_pace`); it is a
    /// mastery pace, never the readiness score. Read-only.
    fn get_study_pace(&mut self, input: MasteryRequest) -> error::Result<StudyPace> {
        let exam_ts = self.get_config_optional::<i64, _>(EXAM_DATE_KEY);
        let has_exam_date = exam_ts.is_some();
        let exam_timestamp = exam_ts.unwrap_or(0);

        // Mastered / total from the same FULL-mastery gate the rest of the engine
        // reports (memory gate AND practice-test performance), so the pace burns
        // down to exactly the Overall-mastery the user sees. Performance is a
        // separate signal attached to the stats before the rollup.
        let mut stats = self.speedrun_subtopic_stats(&input.expected_subtopics)?;
        let perf = self.speedrun_performance_config();
        for s in &mut stats {
            s.performance = perf.get(&s.tag()).copied().unwrap_or_default();
        }
        let counts = crate::speedrun::mastery::mastery_overall(&stats);
        let total_subtopics = counts.subtopics_total;
        let mastered_subtopics = counts.subtopics_mastered;
        let remaining_subtopics = total_subtopics.saturating_sub(mastered_subtopics);

        let now = TimestampSecs::now().0;
        let days_left = if has_exam_date {
            ((exam_timestamp - now) as f64 / 86_400.0).round() as i64
        } else {
            0
        };
        let days_studied = match self.first_graded_review_secs()? {
            Some(first) => ((now - first).max(0) as f64 / 86_400.0).floor() as i64,
            None => 0,
        };

        let pace = compute_mastery_pace(
            remaining_subtopics,
            mastered_subtopics,
            days_studied,
            days_left,
            has_exam_date,
        );
        Ok(StudyPace {
            has_exam_date,
            exam_timestamp,
            days_left,
            remaining_subtopics,
            mastered_subtopics,
            total_subtopics,
            days_studied: days_studied.max(0) as u32,
            current_per_week: pace.current_per_week,
            recommended_per_week: pace.recommended_per_week,
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
    /// The single best next action for a readiness score. This MIRRORS the study
    /// map's "Practice next" heuristic, so the readiness banner's "Do next" and
    /// the map always name the SAME topic: selection is by PERFORMANCE
    /// (practice-test evidence) times exam WEIGHT, not memory/revlog accuracy.
    ///
    /// Over every expected syllabus subtopic, using its exam-importance weight:
    /// skip any subtopic that is already performance-mastered (the map's
    /// "strong"), let `acc` be its practice-test accuracy (a NEVER-practiced
    /// topic counts as fully weak, `acc = 0`), score it `weight * (1 - acc)`, and
    /// take the maximum. Weights come from the same config Python writes from the
    /// topic map (`speedrun_subtopic_weights_config`, treated as equal/1.0 when a
    /// weight is missing) and performance from the same config the mastery query
    /// reads (`speedrun_performance_config`), so both surfaces score identical
    /// data. Iterating `expected` in request (taxonomy) order with a strict `>`
    /// keeps the tie-break (first topic wins) identical to the frontend.
    ///
    /// Always evidence-grounded: it only ever names a real syllabus subtopic, and
    /// distinguishes a never-practiced pick ("not practiced yet") from a measured
    /// one ("N% correct so far") so it never dresses up a missing measurement as
    /// 0%. Falls back to the top study priority when every subtopic is already
    /// performance-mastered, so the action string is never empty.
    fn readiness_next_action(&mut self, expected: &[String]) -> error::Result<String> {
        let stats = self.speedrun_subtopic_stats(expected)?;
        let perf = self.speedrun_performance_config();
        let weights = self.speedrun_subtopic_weights_config();

        let mut best_tag: Option<String> = None;
        let mut best_questions: u32 = 0;
        let mut best_accuracy: f64 = 0.0;
        let mut best_score = -1.0_f64;
        for s in &stats {
            let tag = s.tag();
            let p = perf.get(&tag).copied().unwrap_or_default();
            // Skip performance-mastered subtopics (the map's "strong"): more
            // practice there buys the least readiness.
            if p.mastered() {
                continue;
            }
            // Missing weight -> equal/1.0, matching how the map handles it.
            let weight = weights.get(&tag).copied().unwrap_or(1.0);
            // A never-practiced topic counts as fully weak (acc = 0), so a
            // high-weight topic you have not touched is itself a strong pick.
            let acc = if p.questions > 0 { p.accuracy() } else { 0.0 };
            let score = weight * (1.0 - acc);
            // Strict `>`, so ties keep the FIRST (request/taxonomy-order)
            // subtopic, exactly as the frontend's `score > bestScore` does.
            if score > best_score {
                best_score = score;
                best_tag = Some(tag);
                best_questions = p.questions;
                best_accuracy = p.accuracy();
            }
        }

        if let Some(tag) = best_tag {
            // A never-practiced top-weight topic has no measured accuracy, so
            // "0% correct" would mislead: say it is unpracticed instead.
            let detail = if best_questions == 0 {
                "not practiced yet".to_string()
            } else {
                format!("{:.0}% correct so far", best_accuracy * 100.0)
            };
            return Ok(format!(
                "Focus your weakest area next: {tag} ({detail}), then re-test."
            ));
        }
        // Every subtopic is performance-mastered (or nothing expected): keep the
        // action non-empty with the existing top study priority / generic prompt.
        Ok(match study_priorities(&stats).first() {
            Some(p) => format!("Study {} next, then re-test to narrow the range.", p.tag),
            None => "Keep taking full practice tests to narrow the range.".to_string(),
        })
    }

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

    /// Unix seconds of the FIRST graded review (revlog.id is epoch millis), i.e.
    /// when studying began, used to measure the study history for the mastery
    /// pace. `None` when there are no graded reviews yet (min() over an empty set
    /// is NULL). Read-only.
    fn first_graded_review_secs(&self) -> error::Result<Option<i64>> {
        let first_ms: Option<i64> =
            self.storage
                .db
                .query_row("select min(id) from revlog where ease > 0", [], |row| {
                    row.get(0)
                })?;
        Ok(first_ms.map(|ms| ms / 1000))
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
        memory_recall: None,
    }
}

/// Convert the engine's memory-recall aggregate into the proto message.
fn memory_recall_proto(mr: &crate::speedrun::mastery::MemoryRecallData) -> MemoryRecall {
    MemoryRecall {
        has_data: mr.has_data,
        point: mr.point,
        low: mr.low,
        high: mr.high,
        reviewed_cards: mr.reviewed_cards,
    }
}

/// NoScore when review/coverage gates pass but there is not yet enough graded
/// practice-test evidence to estimate P(pass). Still an honest abstain.
fn no_practice_evidence_no_score(
    graded_reviews: u32,
    coverage_pct: f64,
    questions: u32,
) -> ReadinessResult {
    let need = MIN_PRACTICE_QUESTIONS.saturating_sub(questions);
    ReadinessResult {
        value: Some(readiness_result::Value::NoScore(NoScore {
            reason: format!(
                "Review coverage is met, but a readiness score needs graded practice \
                 tests: {questions}/{MIN_PRACTICE_QUESTIONS} practice-test questions so far."
            ),
            graded_reviews,
            reviews_needed: 0,
            coverage_pct,
            next_best_action: format!(
                "Take a practice test ({need} more graded questions) to unlock a \
                 readiness range."
            ),
        })),
        memory_recall: None,
    }
}

/// A readiness band: the projected 0-10 point + range, P(pass), and confidence.
struct ReadinessBand {
    point: f64,
    low: f64,
    high: f64,
    pass_probability: f64,
    confidence: f64,
}

/// Turn graded practice-test evidence into a readiness band. Pure arithmetic
/// over the counts (deterministic, unit-tested): the projected 0-10 band is
/// 10 x the Wilson 95% interval on the proportion correct, P(pass) is the
/// normal-approx probability the true proportion clears the pass mark, and
/// confidence rises with a tighter band and more coverage. Never fabricated;
/// it only summarises real graded results.
///
/// `questions`/`correct` are f64 so the caller can pass REPRESENTATIVENESS-
/// WEIGHTED evidence: a less representative test contributes a smaller effective
/// sample size, which correctly widens the band (less certain) as well as moving
/// the proportion. Passing the raw integer counts (as f64) is the unweighted
/// special case.
fn readiness_from_practice(questions: f64, correct: f64, coverage_pct: f64) -> ReadinessBand {
    let n = questions.max(1.0);
    let p = (correct / n).clamp(0.0, 1.0);
    let (lo, hi) = wilson_interval_f(correct, questions);
    let scale = |x: f64| (10.0 * x).clamp(0.0, 10.0);
    let se = (p * (1.0 - p) / n).sqrt();
    let pass_probability = if se > 0.0 {
        normal_cdf((p - PASS_PROPORTION) / se)
    } else if p >= PASS_PROPORTION {
        1.0
    } else {
        0.0
    };
    let (point, low, high) = (scale(p), scale(lo), scale(hi));
    let band_conf = (1.0 - (high - low) / 10.0).clamp(0.0, 1.0);
    let confidence = (0.5 * band_conf + 0.5 * coverage_pct).clamp(0.0, 1.0);
    ReadinessBand {
        point,
        low,
        high,
        pass_probability,
        confidence,
    }
}

/// 95% Wilson score interval for a binomial proportion (z = 1.96), integer
/// counts. Robust near 0/1 and for small n, unlike the plain normal
/// approximation. Thin wrapper over the float form.
fn wilson_interval(correct: u32, total: u32) -> (f64, f64) {
    wilson_interval_f(correct as f64, total as f64)
}

/// 95% Wilson score interval on a proportion `correct / total`, with real-valued
/// counts so the effective (representativeness-weighted) sample size can widen
/// the band. `correct` is clamped into `[0, total]` for safety.
fn wilson_interval_f(correct: f64, total: f64) -> (f64, f64) {
    if total <= 0.0 {
        return (0.0, 0.0);
    }
    let z = 1.96_f64;
    let n = total;
    let phat = (correct / n).clamp(0.0, 1.0);
    let z2 = z * z;
    let denom = 1.0 + z2 / n;
    let center = (phat + z2 / (2.0 * n)) / denom;
    let margin = (z / denom) * ((phat * (1.0 - phat) / n) + z2 / (4.0 * n * n)).sqrt();
    (
        (center - margin).clamp(0.0, 1.0),
        (center + margin).clamp(0.0, 1.0),
    )
}

/// Standard normal CDF via an erf approximation (Abramowitz & Stegun 7.1.26,
/// max abs error ~1.5e-7), with no external deps.
fn normal_cdf(z: f64) -> f64 {
    0.5 * (1.0 + erf(z / std::f64::consts::SQRT_2))
}

fn erf(x: f64) -> f64 {
    let t = 1.0 / (1.0 + 0.327_591_1 * x.abs());
    let poly = ((((1.061_405_429 * t - 1.453_152_027) * t + 1.421_413_741) * t - 0.284_496_736)
        * t
        + 0.254_829_592)
        * t;
    let y = 1.0 - poly * (-x * x).exp();
    if x >= 0.0 {
        y
    } else {
        -y
    }
}

#[cfg(test)]
mod tests {
    use anki_proto::speedrun::readiness_result::Value;
    use anki_proto::speedrun::ComputeReadinessRequest;
    use anki_proto::speedrun::MasteryRequest;

    use super::normal_cdf;
    use super::readiness_from_practice;
    use super::wilson_interval;
    use super::PRACTICE_STATS_KEY;
    use crate::collection::Collection;
    use crate::prelude::*;
    use crate::services::SpeedrunService;
    use crate::speedrun::mastery::PERFORMANCE_KEY;
    use crate::speedrun::mastery::SUBTOPIC_WEIGHTS_KEY;
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
    fn meeting_review_gates_still_refuses_without_practice_tests() {
        let mut col = Collection::new();
        // 200 graded reviews AND full practiced coverage, but NO practice-test
        // evidence: readiness must still abstain (P(pass) has nothing to
        // estimate from). The give-up rule holds beyond the review gate.
        for tag in expected() {
            add_reviewed_note(&mut col, &[tag.as_str()], 50);
        }
        match col
            .compute_readiness(request(expected()))
            .unwrap()
            .value
            .unwrap()
        {
            Value::NoScore(no_score) => {
                assert_eq!(no_score.reviews_needed, 0);
                assert!(
                    no_score.reason.to_lowercase().contains("practice"),
                    "unexpected reason: {}",
                    no_score.reason
                );
            }
            Value::Score(_) => panic!("no practice evidence -> must not emit a number"),
        }
    }

    #[test]
    fn emits_a_readiness_band_with_practice_evidence() {
        let mut col = Collection::new();
        for tag in expected() {
            add_reviewed_note(&mut col, &[tag.as_str()], 50); // 200 reviews,
                                                              // full coverage
        }
        // Graded practice-test evidence (78/120 correct) unlocks a real band.
        col.set_config_json(
            PRACTICE_STATS_KEY,
            &serde_json::json!({"questions": 120, "correct": 78, "tests": 4}),
            false,
        )
        .unwrap();
        match col
            .compute_readiness(request(expected()))
            .unwrap()
            .value
            .unwrap()
        {
            Value::Score(s) => {
                // 78/120 = 0.65 -> ~6.5/10, inside its range, pass-prob > 0.5.
                assert!(s.low <= s.point && s.point <= s.high, "band: {s:?}");
                assert!(s.point > 6.0 && s.point < 7.0, "point={}", s.point);
                assert!(s.pass_probability > 0.5);
                assert_eq!(s.coverage_pct, 1.0);
                // Honesty bundle is fully populated (a bare number can't ship).
                assert!(!s.reasons.is_empty());
                assert!(!s.next_best_action.is_empty());
                assert!(s.confidence > 0.0 && s.confidence <= 1.0);
                assert!(s.updated_at > 0);
            }
            Value::NoScore(ns) => panic!("expected a score, got NoScore: {}", ns.reason),
        }
    }

    #[test]
    fn readiness_band_scales_and_bounds() {
        let strong = readiness_from_practice(100.0, 85.0, 1.0);
        assert!(strong.point > 8.0 && strong.point <= 10.0);
        assert!(strong.low <= strong.point && strong.point <= strong.high);
        assert!(strong.pass_probability > 0.9);
        let weak = readiness_from_practice(100.0, 30.0, 1.0);
        assert!(weak.point < 4.0, "point={}", weak.point);
        assert!(weak.pass_probability < 0.1);
    }

    #[test]
    fn weighted_evidence_widens_the_band_versus_raw() {
        // Same proportion (80%), but only a fraction of the questions are
        // "representative" evidence. The weighted band is centred at the same
        // point yet WIDER (a smaller effective sample size is less certain), so
        // less representative practice moves readiness less confidently.
        let raw = readiness_from_practice(100.0, 80.0, 1.0);
        let weighted = readiness_from_practice(40.0, 32.0, 1.0);
        assert!((raw.point - weighted.point).abs() < 1e-9, "same proportion");
        let raw_width = raw.high - raw.low;
        let weighted_width = weighted.high - weighted.low;
        assert!(
            weighted_width > raw_width,
            "weighted width {weighted_width} should exceed raw width {raw_width}"
        );
    }

    #[test]
    fn band_uses_weighted_proportion_when_present() {
        // Raw counts read 50% correct, but the weighted evidence (the
        // representative tests) reads 80% correct. The BAND must follow the
        // WEIGHTED proportion (~8/10), not the raw one (~5/10), while the give-up
        // gate still passes on the RAW question count (120 >= 30).
        let mut col = Collection::new();
        for tag in expected() {
            add_reviewed_note(&mut col, &[tag.as_str()], 50); // 200 reviews, full coverage
        }
        col.set_config_json(
            PRACTICE_STATS_KEY,
            &serde_json::json!({
                "questions": 120, "correct": 60, "tests": 4,
                "weighted_questions": 60.0, "weighted_correct": 48.0,
            }),
            false,
        )
        .unwrap();
        match col
            .compute_readiness(request(expected()))
            .unwrap()
            .value
            .unwrap()
        {
            Value::Score(s) => {
                assert!(s.point > 7.0, "weighted 80% -> ~8/10, got {}", s.point);
                assert!(s.pass_probability > 0.5);
            }
            Value::NoScore(ns) => panic!("expected a weighted score, got NoScore: {}", ns.reason),
        }
    }

    #[test]
    fn give_up_gate_uses_raw_question_count_not_weighted() {
        // 30 RAW graded questions clears the practice gate even though the
        // weighted evidence is tiny (a pile of low-representativeness drills):
        // the give-up rule counts real questions answered, not their weight.
        let mut col = Collection::new();
        for tag in expected() {
            add_reviewed_note(&mut col, &[tag.as_str()], 50);
        }
        col.set_config_json(
            PRACTICE_STATS_KEY,
            &serde_json::json!({
                "questions": 30, "correct": 24, "tests": 3,
                "weighted_questions": 8.4, "weighted_correct": 6.72,
            }),
            false,
        )
        .unwrap();
        match col
            .compute_readiness(request(expected()))
            .unwrap()
            .value
            .unwrap()
        {
            Value::Score(s) => assert!(s.low <= s.point && s.point <= s.high),
            Value::NoScore(ns) => panic!("30 raw questions must clear the gate: {}", ns.reason),
        }
    }

    #[test]
    fn wilson_interval_brackets_the_estimate() {
        let (lo, hi) = wilson_interval(50, 100);
        assert!(lo < 0.5 && 0.5 < hi);
        assert!((0.0..=1.0).contains(&lo) && (0.0..=1.0).contains(&hi));
        // Zero total -> degenerate (0, 0), never a panic.
        assert_eq!(wilson_interval(0, 0), (0.0, 0.0));
    }

    #[test]
    fn normal_cdf_is_calibrated_at_known_points() {
        assert!((normal_cdf(0.0) - 0.5).abs() < 1e-6);
        assert!(normal_cdf(3.0) > 0.99 && normal_cdf(-3.0) < 0.01);
        assert!(normal_cdf(1.0) > normal_cdf(0.0));
    }

    #[test]
    fn coverage_is_weighted_by_unit_weights() {
        let mut col = Collection::new();
        // Two units, one subtopic each; practice only the heavy unit "b".
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
                subtopic_prereqs: vec![],
                unit_prereqs: vec![],
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
                subtopic_prereqs: vec![],
                unit_prereqs: vec![],
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
            subtopic_prereqs: vec![],
            unit_prereqs: vec![],
        }
    }

    #[test]
    fn study_pace_reports_subtopic_counts_without_exam_date() {
        // No exam date: report the measured subtopic counts (total from the
        // expected syllabus, none mastered yet) but never claim on/off track.
        let mut col = Collection::new();
        let pace = col.get_study_pace(pace_req()).unwrap();
        assert!(!pace.has_exam_date);
        assert_eq!(pace.total_subtopics, 2);
        assert_eq!(pace.mastered_subtopics, 0);
        assert_eq!(pace.remaining_subtopics, 2);
        assert_eq!(pace.projected_days_to_finish, 0);
        assert!(!pace.on_track);
    }

    #[test]
    fn study_pace_gathers_before_projecting_when_nothing_mastered() {
        // Reviews exist (a study history) but nothing has cleared its mastery
        // gate yet, so we show the needed rate but abstain from a projection /
        // verdict, which is the give-up rule applied to the pace.
        let mut col = Collection::new();
        add_reviewed_note(&mut col, &["subtopic::general::a"], 5);
        let now = crate::timestamp::TimestampSecs::now().0;
        col.set_config_json("speedrunExamDate", &(now + 100 * 86_400), false)
            .unwrap();
        let pace = col.get_study_pace(pace_req()).unwrap();
        assert!(pace.has_exam_date);
        assert_eq!(pace.mastered_subtopics, 0);
        assert_eq!(pace.remaining_subtopics, 2);
        // Nothing mastered -> the observed rate is undefined, so no projection.
        assert_eq!(pace.projected_days_to_finish, 0);
        assert!(!pace.on_track);
        // The rate needed to finish in time is still shown (2 left over ~14 wk).
        assert!(pace.recommended_per_week > 0.0);
    }

    // ---- readiness_next_action: performance x exam-weight selection ----
    //
    // The banner's "Do next" MIRRORS the study map's "Practice next": pick the
    // subtopic maximising exam-weight x (1 - performance accuracy), skipping any
    // that is already performance-mastered, with a never-practiced topic counting
    // as fully weak (acc = 0). These helpers write the SAME config the map reads
    // (performance + subtopic weights), so the two surfaces score identical data.

    fn set_perf(col: &mut Collection, entries: &[(&str, u32, u32)]) {
        let mut map = serde_json::Map::new();
        for (tag, q, c) in entries {
            map.insert(
                (*tag).to_string(),
                serde_json::json!({ "questions": q, "correct": c }),
            );
        }
        col.set_config_json(PERFORMANCE_KEY, &serde_json::Value::Object(map), false)
            .unwrap();
    }

    fn set_weights(col: &mut Collection, entries: &[(&str, f64)]) {
        let mut map = serde_json::Map::new();
        for (tag, w) in entries {
            map.insert((*tag).to_string(), serde_json::json!(w));
        }
        col.set_config_json(SUBTOPIC_WEIGHTS_KEY, &serde_json::Value::Object(map), false)
            .unwrap();
    }

    /// Pure Rust twin of the frontend `practiceNextTag` (study-map +page.svelte):
    /// same skip-if-performance-mastered, same acc=0 for a never-practiced topic,
    /// same `weight * (1 - acc)` score, same strict-`>` first-in-order tie-break.
    /// Lets a test assert the engine names the SAME topic the map would, on
    /// identical data.
    fn map_practice_next(
        expected: &[&str],
        weights: &[(&str, f64)],
        perf: &[(&str, u32, u32)],
    ) -> String {
        let w: std::collections::HashMap<&str, f64> = weights.iter().copied().collect();
        let p: std::collections::HashMap<&str, (u32, u32)> =
            perf.iter().map(|(t, q, c)| (*t, (*q, *c))).collect();
        let mut best = String::new();
        let mut best_score = -1.0_f64;
        for tag in expected {
            let (q, c) = p.get(tag).copied().unwrap_or((0, 0));
            let acc = if q > 0 { c as f64 / q as f64 } else { 0.0 };
            if q >= 5 && acc >= 0.80 {
                continue; // performance-mastered ("strong") -> skip
            }
            let weight = w.get(tag).copied().unwrap_or(1.0);
            let score = weight * (1.0 - acc);
            if score > best_score {
                best_score = score;
                best = (*tag).to_string();
            }
        }
        best
    }

    #[test]
    fn next_action_selects_by_performance_times_exam_weight() {
        // c has the max weight x (1 - acc); b has the highest RAW weight but is
        // performance-mastered, so it is skipped, not chosen. This is the map's
        // logic, not memory/revlog accuracy.
        let mut col = Collection::new();
        let a = "subtopic::general::a";
        let b = "subtopic::univariate::b";
        let c = "subtopic::multivariate::c";
        set_weights(&mut col, &[(a, 1.0), (b, 10.0), (c, 5.0)]);
        set_perf(&mut col, &[(a, 10, 5), (b, 10, 9), (c, 10, 6)]); // 0.5 / 0.9 / 0.6
        let expected = vec![a.to_string(), b.to_string(), c.to_string()];
        let msg = col.readiness_next_action(&expected).unwrap();
        assert!(msg.contains(c), "should pick c (weight 5 x 0.4 = 2.0): {msg}");
        assert!(!msg.contains(b), "mastered b must be skipped: {msg}");
        assert!(msg.contains("60% correct so far"), "measured detail: {msg}");
        // The engine names the SAME topic the map's practiceNextTag would.
        assert!(msg.contains(&map_practice_next(
            &[a, b, c],
            &[(a, 1.0), (b, 10.0), (c, 5.0)],
            &[(a, 10, 5), (b, 10, 9), (c, 10, 6)],
        )));
    }

    #[test]
    fn next_action_never_practiced_top_weight_uses_honest_wording() {
        // A high-weight, never-practiced topic (acc = 0) outscores a practiced
        // but lower-weight one, and is reported as "not practiced yet", never as
        // a fabricated "0% correct".
        let mut col = Collection::new();
        let a = "subtopic::general::a";
        let b = "subtopic::univariate::b";
        set_weights(&mut col, &[(a, 1.0), (b, 10.0)]);
        set_perf(&mut col, &[(a, 10, 5)]); // b has no practice-test evidence
        let expected = vec![a.to_string(), b.to_string()];
        let msg = col.readiness_next_action(&expected).unwrap();
        assert!(msg.contains(b), "high-weight never-practiced b wins: {msg}");
        assert!(msg.contains("not practiced yet"), "honest wording: {msg}");
        assert!(!msg.contains("correct"), "no fabricated 0%: {msg}");
        assert_eq!(
            map_practice_next(&[a, b], &[(a, 1.0), (b, 10.0)], &[(a, 10, 5)]),
            b
        );
    }

    #[test]
    fn next_action_tie_breaks_to_first_in_request_order() {
        // Two equal-weight, never-practiced topics tie; the strict `>` keeps the
        // FIRST in request (taxonomy) order, exactly like the frontend, so the
        // banner and map never disagree on a tie.
        let mut col = Collection::new();
        let first = "subtopic::univariate::discrete_dists";
        let second = "subtopic::univariate::continuous_dists";
        set_weights(&mut col, &[(first, 9.0), (second, 9.0)]);
        let expected = vec![first.to_string(), second.to_string()];
        let msg = col.readiness_next_action(&expected).unwrap();
        assert!(
            msg.contains(first) && !msg.contains(second),
            "first-in-order wins the tie: {msg}"
        );
    }

    #[test]
    fn next_action_falls_back_when_all_performance_mastered() {
        // No eligible (not-strong) subtopic -> fall back to a non-empty study
        // priority, so the honesty bundle's action is never empty.
        let mut col = Collection::new();
        let a = "subtopic::general::a";
        let b = "subtopic::univariate::b";
        set_weights(&mut col, &[(a, 1.0), (b, 2.0)]);
        set_perf(&mut col, &[(a, 10, 10), (b, 10, 10)]); // both mastered
        let expected = vec![a.to_string(), b.to_string()];
        let msg = col.readiness_next_action(&expected).unwrap();
        assert!(!msg.is_empty(), "fallback must never be empty");
        assert!(msg.starts_with("Study "), "top-priority fallback: {msg}");
    }
}
