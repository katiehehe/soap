# SPEC_CHECKLIST.md — living compliance & grade tracker

> The agent re-reads this at the start of every session, states which deadline + item it's on, and
> updates the checkboxes + "files touched" before every commit. This mirrors the grading rubric so
> drift shows up early. `[ ]` = not started · `[~]` = in progress · `[x]` = done + proof captured.

## 0. Automatic-fail guards (check on EVERY commit)

- [x] No made-up / misleading readiness number anywhere. Give-up rule returns `NoScore` under threshold. (Rust `compute_readiness` returns a `oneof {NoScore, ReadinessScore}`; thresholds ≥200 reviews AND ≥50% coverage; 3 Rust + 1 Python tests.)
- [x] Leakage scan run and clean (no test item or near-copy in training data). (`anki/speedrun/evalsplit.py` + `tools/speedrun/leakage_scan.py`; ran clean on the seed deck; `test_speedrun_split.py`.)
- [ ] Every AI output has a traceable named source.
- [ ] Both apps run with AI switched OFF and still give a score.
- [ ] License: AGPL-3.0-or-later, Anki credited (BSD-3-Clause parts noted).

## 1. Grade caps to avoid

- [x] Real Rust engine change exists (else 50% cap). (`SpeedrunService` in the `anki` crate: 7 RPCs called from Python — `speedrun_ping`, `compute_readiness`, `get_mastery_state`, `get_mastery_ordered_new_cards`, `get_points_at_stake_order`, `get_study_plan`, `get_study_pace` — plus two opt-in, default-off live-queue reorders in `build_queues`: `speedrunMasteryScheduler` (new-card tier order) and `speedrunPointsAtStake` (review order).)
- [~] Phone companion shares the engine AND syncs (else 70% cap). Engine-sharing DONE: AnkiDroid APK built from our fork's engine (`librsdroid.so` arm64), installed + running on the `Medium_Phone` emulator (`nativeloader` loads our engine "ok"; `makeBackendUsable` succeeds). Two-way SYNC is the Friday item.
- [x] Re-runnable test setup with seed (else 60% cap). (`train_test_split(seed)` is deterministic; Rust + Python tests re-run identically.)
- [x] Held-out testing in place (else 60% cap). (seeded held-out split in `anki/speedrun/evalsplit.py` + leakage gate.)
- [ ] Both apps install/run on a clean device (else 50% cap).

## 2. Rubric coverage (target = the 20/20/15/15/12/10/8 split)

- [ ] Rust change & fit (20%)
- [ ] Score accuracy & honest uncertainty (20%)
- [ ] Study feature on learning science (15%)
- [ ] AI checking & safety (15%)
- [ ] Fair, re-runnable tests (12%)
- [ ] Desktop + phone share one engine, sync works (10%)
- [ ] Useful product & clean UX, both apps (8%)

## 3. WEDNESDAY — core works on both screens, NO AI

Desktop:

- [x] Anki forked and building from source (`./ninja pylib qt` green; `./run` launch path verified; engine+pylib open/close a collection headlessly).
- [x] Rust change working end-to-end: the diff, **3 Rust unit tests**, **1 Python-calling test** (`SpeedrunPing`); plus `ComputeReadiness` with 3 Rust + 1 Python tests.
- [x] Review loop running on the Exam P deck (seed script builds a 42-card tagged deck spanning all 19 subtopics across the 3 units; scheduler draws + answers cards; revlog grows).
- [x] Give-up rule done in Rust with a range-capable score type (`oneof {NoScore, ReadinessScore}`). FSRS memory-calibration harness built (`make calibration` + `calibration.py`); a calibrated readiness number stays withheld until the performance model exists (honest abstain, never fabricated).
- [x] Desktop installer built + verified: `out/installer/dist/anki-25.09.99-mac-apple.dmg` (225 MB drag-install DMG; mounts cleanly, contains `Anki.app` v25.9.99 with the executable + Applications symlink). Final clean-machine launch is a manual check on a device without the dev toolchain.
      Mobile:
- [x] Shared Rust engine on the phone: backend `anki` submodule repointed at our fork, `.aar` + `librsdroid.so` (arm64-v8a) rebuilt from our engine, `local_backend=true`. The only cross-version break was one non-exhaustive `when` (AnkiDroid `Deck.kt`) over the newer `Order.RELATIVE_OVERDUENESS`; adding that branch made `assemblePlayDebug` report `BUILD SUCCESSFUL`. APK embeds `lib/arm64-v8a/librsdroid.so`; installs + runs on the `Medium_Phone` emulator (DeckPicker up, our engine loaded). Recipe in `docs/android-build.md`; proof screenshot `docs/android-emulator.png`.
- [~] App runs on our engine and reads a real collection on-device (deck list + due counts rendered by our backend). Loading the Exam P deck + a full phone review session is the remaining step (export a `.colpkg` from desktop or sync). (Two-way sync NOT required yet.)
  Proof to capture: commit hash · clean-build recording · test results · clean-machine install recording · phone review-session recording.

## 4. FRIDAY — AI added & checked; phone syncs

Desktop (AI):

- [ ] Short note: what AI was built, why, what was skipped.
- [ ] Every AI output traces to a named source.
- [ ] Eval runs before students see anything: accuracy + wrong-answer rate on a held-out set, with the cutoff.
- [ ] Side-by-side: AI beats a simpler method (keyword/vector).
- [ ] App still scores with AI off.
      Mobile:
- [ ] Two-way sync works (review on phone → shows on desktop and reverse; no lost/double reviews).
- [ ] Offline review works, then syncs on reconnect.
- [ ] Phone shows the three scores with ranges and follows the give-up rule.
      Proof: eval numbers + baseline comparison · recording of a phone-reviewed card appearing on desktop after sync.

## 5. SUNDAY — prove it, ship both

- [~] Memory model calibrated: reproducible harness built (`make calibration` → FSRS held-out log loss + RMSE(bins); `calibration.py` metrics unit-tested). Produces the chart/numbers on a real review history; abstains honestly otherwise.
- [~] Performance model: accuracy on held-out exam-style questions. Pipeline BUILT — a deterministic calibrated logistic model (`pylib/anki/speedrun/performance.py`) with a seeded held-out split + leakage scan + calibration + majority-class baseline; validated end-to-end on a synthetic fixture via `make performance` (beats baseline, calibrated). Awaiting a real labelled disguised-item dataset; abstains ("not yet measured") until then.
- [~] Score mapping written down, with a range: `docs/score-models.md` (memory/performance/readiness, give-up rule, honesty bundle). Readiness stays `NoScore` until the performance model is calibrated.
- [~] Study feature tested with 3 builds, equal study time: (1) full three-tier scheduler, (2) within-unit interleaving removed → global mixed pool, (3) plain Anki. All three are now selectable via config: build 1 = `speedrunMasteryScheduler` on + `speedrunAblateWithinUnit` off; build 2 = both on; build 3 = scheduler off (plain). The Full-vs-Ablated ordering difference is covered by Rust tests. The RUN + pre-registered metric + nulls are still to be executed (`docs/study-feature-ablation.md`).
- [ ] Honest reporting, including results that did not work.
- [ ] Packaged desktop installer + packaged phone build (signed APK, or iOS TestFlight/sideload).
- [ ] Sync conflict handling correct + documented.
- [ ] Both apps run with AI off and still give a score.
      Proof: results report · model descriptions · Brainlift · recordings of both builds installing + running on clean devices.

## 6. Concrete challenges (section 7)

- [x] 7a Rust change: the real three-tier mastery-gated scheduler exists AND is wired into the **live** new-card queue behind an opt-in, default-off config flag (`speedrunMasteryScheduler`) in `Collection::build_queues` — read-only, so undo/integrity are untouched, and off by default so upstream behaviour and the ablation's plain-Anki baseline are unchanged. Mastery model (per-subtopic gate from revlog accuracy + FSRS retrievability), `GetMasteryState` (now also **importance-weighted rollups** + a **"what to study next"** ranking + a tier-aware recommendation) + `GetMasteryOrderedNewCards`, `GetPointsAtStakeOrder` (due cards by topic weight × student weakness), `GetStudyPlan` (today's decks grouped by tier — blocked → within-unit → cross-unit — each with Anki's own daily-limit-capped due/new counts, so the tiers are visible as a **daily plan**, not just an invisible reorder), and `GetStudyPace` (coverage pace vs the user's exam date: new cards remaining ÷ days left, so the student knows if they're on track to cover the syllabus — plus a "Study more today" one-click extend of today's new limit for heavy days) RPCs; a second opt-in flag `speedrunPointsAtStake` brings weak-topic due cards back sooner in the live review queue (order-only, FSRS intervals valid, undo works). Tier/pool ordering. ~51 Rust tests + Python tests for every RPC; undo/no-corruption covered (Python undo test with both flags on; `make crash-test` 20× SIGKILL clean); mastery query revlog-driven (p95 ~0.06ms), ordered-new-cards p95 ~155ms on 50k; `docs/rust-change.md` (why Rust) + `docs/upstream-touched.md` (merge note, incl. the two `build_queues` reorder hooks and the read-only `deck_tree` use for the plan).
- [ ] 7b Sync test: 10 offline phone + 10 offline desktop → all 20 land once; same-card conflict rule picks a clear winner (documented).
- [x] 7c Coverage map: official 2026-05 P outline in `pylib/anki/speedrun/exam_p_topics.json` (3 units, 19 subtopics from the real learning outcomes); coverage computed in Rust from note tags, weighted by section; % shown on the readiness dashboard; readiness abstains below 50% (give-up rule). An interactive **study map** (`ts/routes/study-map`) renders the syllabus as an importance-sized bubble concept map (Exam P centre, units on an equilateral triangle, subtopics radiating; bubble size = exam weight, colour = measured mastery) with a "what to study next" ranking, via `get_mastery_state`, plus a **"Today's plan"** panel (via `get_study_plan`) that lists the decks to study now grouped by tier with today's real due/new counts, each opening its deck by id, and an **"Exam pace"** card (via `get_study_pace`) that turns a target exam date into an honest coverage pace (on-track/behind, recommended new/day) with a "Study more today" lever to go beyond the daily quota.
- [ ] 7d Paraphrase test: 30 cards × 2 reworded Qs; recall vs reworded accuracy; gap reported.
- [x] 7e Leakage check: `tools/speedrun/leakage_scan.py` flags verbatim + near-copy (Jaccard) test items in training and exits non-zero; ran clean on the seed deck; `test_speedrun_split.py` covers detection + a deterministic seeded split.
- [ ] 7f AI card check: gold set of 50; 50 generated from one source; correct/wrong/bad-teaching counts; cutoff pre-set.
- [~] 7g Crash + offline: desktop `make crash-test` kills the app mid-review 20× with zero corruption (SQLite integrity_check). Network/AI-off path is Friday (no AI yet); phone crash pending.
- [x] 7h One-command benchmark: `make bench` on a 50k-card deck prints p50/p95/worst per action. Latest run (all-new deck): next-card p95 ~0.05ms, mastery query p95 ~0.06ms, mastery-ordered new cards p95 ~155ms, readiness p95 ~4.7ms. The mastery query is now revlog-driven (scans only reviewed cards, so it scales with review count, not deck size); the ordered-new-cards path still scans all new cards and dropped from p95 ~1.39s → ~155ms after that optimisation + a precomputed-rank sort.

## 7. Score-model steps (section 9)

- [~] Step 1 (req): memory calibrated, proven on held-back reviews. Reproducible harness built: `make calibration` runs FSRS's held-out (time-series split) log loss + RMSE via the engine, and `pylib/anki/speedrun/calibration.py` (Brier/log loss/ECE/reliability bins, unit-tested) is the reusable metrics layer. Abstains honestly on a thin history (needs a real study history to print numbers).
- [~] Step 2 (req): predict held-back exam-style question correctness (mastery, difficulty, timing, coverage). Pipeline built (`performance.py` + `make performance`) and validated on a synthetic fixture (seeded, leakage-clean, calibrated, beats baseline); awaiting a real disguised-item dataset — reads "not yet measured" until then (never fabricated).
- [~] Step 3 (req): turn performance into a score, method written down (`docs/score-models.md`), range shown. Give-up rule live in Rust; readiness stays `NoScore` until the performance model is calibrated (no invented number).
- [ ] Step 4 (bonus): validate against real students with study history + practice-test scores.

## 8. Speed & reliability targets (section 10) — report p50 / p95 / worst

- [ ] Button press acknowledged: p95 < 50 ms (desktop + phone).
- [x] Next card after grading: p95 < 100 ms. (measured p95 ~0.05 ms on 50k via `make bench`.)
- [x] Dashboard first load: p95 < 1 s. Refresh: p95 < 500 ms, no freeze. (on 50k via `make bench`: mastery query p95 ~0.06 ms + readiness p95 ~4.7 ms power the dashboard, and mastery-ordered new cards p95 ~155 ms — all comfortably under both the 1 s load and 500 ms refresh targets after the revlog-driven query optimisation.)
- [ ] Sync of a normal session: < 5 s on a normal connection.
- [ ] Memory on 50k cards: under a stated limit, desktop + mid-range phone.
- [ ] Cold start: < 5 s desktop, < 4 s phone. Nothing freezes the screen > 100 ms.
- [~] Zero corrupted collections in the crash test. (desktop: 20× mid-review SIGKILL, integrity_check ok every time via `make crash-test`; phone pending.)

## 9. Hand-in (section 12) — due Sunday 10:59 PM CT

- [ ] Public AGPL-3.0-or-later fork, Anki credited, exam stated up front, build instructions for both apps, architecture overview, Rust-change note, files-touched list.
- [ ] Demo video (3–5 min): review session · Rust change in action · card synced phone→desktop · three scores with ranges · AI features · test results.
- [ ] Model descriptions: one page each for memory / performance / readiness, incl. the give-up rule.
- [ ] Brainlift (per Patrick's outline).

## Files touched upstream (keep current for the merge-difficulty note)

See `docs/upstream-touched.md` for the full log. Summary of upstream Anki files modified:

- `rslib/src/lib.rs` — `pub mod speedrun;` (1 line) — low.
- `rslib/proto/src/lib.rs` — `protobuf!(speedrun, "speedrun");` (1 line) — low.
- `rslib/proto/python.rs` — `import anki.speedrun_pb2` in the generated-header list (1 line) — low/med.
- `qt/aqt/mediasrv.py` — add `readiness-dashboard` route + expose `compute_readiness` (2 list entries) — med.
- `qt/aqt/main.py` — add a Tools-menu action + `on_speedrun_readiness` handler — med.
- `rslib/src/scheduler/queue/builder/mod.rs` — two opt-in reorder hooks in `build_queues`: new cards by mastery tier (`speedrunMasteryScheduler`) and due review cards by points-at-stake (`speedrunPointsAtStake`); both default off and read-only — low/med.
  New files (no merge risk): `proto/anki/speedrun.proto`, `rslib/src/speedrun/*` (service + mastery), `qt/aqt/speedrun.py`, `ts/routes/readiness-dashboard/+page.svelte`, `ts/routes/study-map/*` (bubble concept map + geometry lib/tests), `pylib/anki/speedrun/*` (topics + weights, seed, evalsplit, calibration), `tools/speedrun/*` (deck builder, bench, crash_test, leakage_scan, `evals/memory_calibration.py`), `Makefile`, `pylib/tests/test_speedrun*.py`, `ts/tests/e2e/readiness-dashboard.test.ts`, `ts/tests/e2e/study-map.test.ts`, `docs/rust-change.md`, `docs/upstream-touched.md`, `docs/android-build.md`, `docs/fsrs-reference.md`, `docs/vision.md`, `docs/demo-script.md`, `docs/ai-features-prd.md`, `docs/score-models.md`, `docs/overnight-progress.md`.
