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

- [x] Real Rust engine change exists (else 50% cap). (`SpeedrunService` in the `anki` crate: `speedrun_ping` + `compute_readiness`, new protobuf message called from Python.)
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
- [x] Review loop running on the Exam P deck (seed script builds 6 tagged cards across 3 units; scheduler draws + answers cards; revlog grows).
- [~] Give-up rule done in Rust with a range-capable score type; FSRS memory calibration + range is a Sunday item.
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

- [ ] Memory model calibrated: calibration chart + Brier/log loss on held-out reviews.
- [ ] Performance model: accuracy on held-out exam-style questions.
- [ ] Score mapping written down, with a range.
- [ ] Study feature tested with 3 builds, equal study time: (1) full three-tier scheduler, (2) within-unit interleaving removed → global mixed pool, (3) plain Anki. Metric pre-registered; nulls reported.
- [ ] Honest reporting, including results that did not work.
- [ ] Packaged desktop installer + packaged phone build (signed APK, or iOS TestFlight/sideload).
- [ ] Sync conflict handling correct + documented.
- [ ] Both apps run with AI off and still give a score.
      Proof: results report · model descriptions · Brainlift · recordings of both builds installing + running on clean devices.

## 6. Concrete challenges (section 7)

- [~] 7a Rust change: the real three-tier mastery-gated scheduler now exists — mastery model (per-subtopic gate from revlog accuracy + FSRS retrievability), `GetMasteryState` + `GetMasteryOrderedNewCards` RPCs, tier/pool ordering. 11 Rust tests + 4 Python tests; undo/no-corruption covered; `docs/rust-change.md` (why Rust) + `docs/upstream-touched.md` (merge note). Remaining: wire ordering into the live queue builder (phone build now verified — engine runs on the emulator).
- [ ] 7b Sync test: 10 offline phone + 10 offline desktop → all 20 land once; same-card conflict rule picks a clear winner (documented).
- [x] 7c Coverage map: official 2026-05 P outline in `pylib/anki/speedrun/exam_p_topics.json` (3 units, 19 subtopics from the real learning outcomes); coverage computed in Rust from note tags, weighted by section; % shown on the readiness dashboard; readiness abstains below 50% (give-up rule). An interactive **study map** (`ts/routes/study-map`) renders the syllabus as a concept map (Exam P centre, units on an equilateral triangle, subtopics radiating) with links that fill by mastery via `get_mastery_state`.
- [ ] 7d Paraphrase test: 30 cards × 2 reworded Qs; recall vs reworded accuracy; gap reported.
- [x] 7e Leakage check: `tools/speedrun/leakage_scan.py` flags verbatim + near-copy (Jaccard) test items in training and exits non-zero; ran clean on the seed deck; `test_speedrun_split.py` covers detection + a deterministic seeded split.
- [ ] 7f AI card check: gold set of 50; 50 generated from one source; correct/wrong/bad-teaching counts; cutoff pre-set.
- [~] 7g Crash + offline: desktop `make crash-test` kills the app mid-review 20× with zero corruption (SQLite integrity_check). Network/AI-off path is Friday (no AI yet); phone crash pending.
- [x] 7h One-command benchmark: `make bench` on a 50k-card deck prints p50/p95/worst per action (next-card p95 ~0.06ms, mastery query p50 ~160ms, readiness p50 ~356ms).

## 7. Score-model steps (section 9)

- [ ] Step 1 (req): memory calibrated, proven on held-back reviews.
- [ ] Step 2 (req): predict held-back exam-style question correctness (mastery, difficulty, timing, coverage).
- [ ] Step 3 (req): turn performance into a score, method written down, range shown.
- [ ] Step 4 (bonus): validate against real students with study history + practice-test scores.

## 8. Speed & reliability targets (section 10) — report p50 / p95 / worst

- [ ] Button press acknowledged: p95 < 50 ms (desktop + phone).
- [x] Next card after grading: p95 < 100 ms. (measured p95 ~0.06 ms on 50k via `make bench`.)
- [~] Dashboard first load: p95 < 1 s. Refresh: p95 < 500 ms, no freeze. (readiness p95 ~553 ms on 50k — under the 1s load target; refresh borderline, to optimise.)
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
  New files (no merge risk): `proto/anki/speedrun.proto`, `rslib/src/speedrun/*` (service + mastery), `qt/aqt/speedrun.py`, `ts/routes/readiness-dashboard/+page.svelte`, `ts/routes/study-map/+page.svelte`, `pylib/anki/speedrun/*` (topics, seed, evalsplit), `tools/speedrun/*` (deck builder, bench, crash_test, leakage_scan), `Makefile`, `pylib/tests/test_speedrun*.py`, `ts/tests/e2e/readiness-dashboard.test.ts`, `ts/tests/e2e/study-map.test.ts`, `docs/rust-change.md`, `docs/upstream-touched.md`, `docs/android-build.md`, `docs/fsrs-reference.md`, `docs/vision.md`, `docs/demo-script.md`, `docs/ai-features-prd.md`.
