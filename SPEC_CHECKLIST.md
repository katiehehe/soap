# SPEC_CHECKLIST.md — living compliance & grade tracker

> The agent re-reads this at the start of every session, states which deadline + item it's on, and
> updates the checkboxes + "files touched" before every commit. This mirrors the grading rubric so
> drift shows up early. `[ ]` = not started · `[~]` = in progress · `[x]` = done + proof captured.

## 0. Automatic-fail guards (check on EVERY commit)
- [ ] No made-up / misleading readiness number anywhere. Give-up rule returns `NoScore` under threshold.
- [ ] Leakage scan run and clean (no test item or near-copy in training data).
- [ ] Every AI output has a traceable named source.
- [ ] Both apps run with AI switched OFF and still give a score.
- [ ] License: AGPL-3.0-or-later, Anki credited (BSD-3-Clause parts noted).

## 1. Grade caps to avoid
- [ ] Real Rust engine change exists (else 50% cap).
- [ ] Phone companion shares the engine AND syncs (else 70% cap).
- [ ] Re-runnable test setup with seed (else 60% cap).
- [ ] Held-out testing in place (else 60% cap).
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
- [ ] Anki forked and building from source (`./run` launches your fork).
- [ ] Rust change working end-to-end: the diff, **3 Rust unit tests**, **1 Python-calling test**.
- [ ] Review loop running on the Exam P deck.
- [ ] Memory model running with an honest score: a range + the give-up rule.
- [ ] Desktop installer runs on a clean machine.
Mobile:
- [ ] Phone app builds + runs on a real device/emulator.
- [ ] Loads the Exam P deck and runs a real review session on the shared engine. (Two-way sync NOT required yet.)
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
- [ ] 7a Rust change: ≥3 Rust tests + 1 Python test; undo works + no corruption; one-page "why Rust"; upstream-files-touched + merge-difficulty note; verified on phone build.
- [ ] 7b Sync test: 10 offline phone + 10 offline desktop → all 20 land once; same-card conflict rule picks a clear winner (documented).
- [ ] 7c Coverage map: every official P topic listed, covered ones marked, % shown on dashboard, abstains below the line.
- [ ] 7d Paraphrase test: 30 cards × 2 reworded Qs; recall vs reworded accuracy; gap reported.
- [ ] 7e Leakage check: script flags test items/near-copies in training; result clean.
- [ ] 7f AI card check: gold set of 50; 50 generated from one source; correct/wrong/bad-teaching counts; cutoff pre-set.
- [ ] 7g Crash + offline: kill each app mid-review 20× → zero corruption; network pull → AI off cleanly, apps keep working + still score.
- [ ] 7h One-command benchmark: `make bench` on the 50k-card deck prints p50/p95/worst per action.

## 7. Score-model steps (section 9)
- [ ] Step 1 (req): memory calibrated, proven on held-back reviews.
- [ ] Step 2 (req): predict held-back exam-style question correctness (mastery, difficulty, timing, coverage).
- [ ] Step 3 (req): turn performance into a score, method written down, range shown.
- [ ] Step 4 (bonus): validate against real students with study history + practice-test scores.

## 8. Speed & reliability targets (section 10) — report p50 / p95 / worst
- [ ] Button press acknowledged: p95 < 50 ms (desktop + phone).
- [ ] Next card after grading: p95 < 100 ms.
- [ ] Dashboard first load: p95 < 1 s. Refresh: p95 < 500 ms, no freeze.
- [ ] Sync of a normal session: < 5 s on a normal connection.
- [ ] Memory on 50k cards: under a stated limit, desktop + mid-range phone.
- [ ] Cold start: < 5 s desktop, < 4 s phone. Nothing freezes the screen > 100 ms.
- [ ] Zero corrupted collections in the crash test, both platforms.

## 9. Hand-in (section 12) — due Sunday 10:59 PM CT
- [ ] Public AGPL-3.0-or-later fork, Anki credited, exam stated up front, build instructions for both apps, architecture overview, Rust-change note, files-touched list.
- [ ] Demo video (3–5 min): review session · Rust change in action · card synced phone→desktop · three scores with ranges · AI features · test results.
- [ ] Model descriptions: one page each for memory / performance / readiness, incl. the give-up rule.
- [ ] Brainlift (per Patrick's outline).

## Files touched upstream (keep current for the merge-difficulty note)
- (add as you go: path — what changed — merge risk low/med/high)
