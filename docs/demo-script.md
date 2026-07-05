# Demo script — SOA Exam P Speedrun (hand-in video)

This is the script for the **3–5 minute hand-in demo video** (`docs/project-brief.md`
§12), mapped to the **six required shots**, plus how to run the phone emulator,
how to prove the engine is ours, and how to install on a clean device.

**Stay honest (it's graded).** A made-up readiness number or a faked sync/AI clip
is an _automatic fail_. All six shots are now built and measured, with **one**
capture still outstanding: the **on-device phone→desktop sync recording** (the
sync code path itself is tested green via `make sync-test`; only the screen
recording on the phone remains). Do **not** stage it — record the real thing.

## The six required shots (§12) → where they are

| #  | Required shot               | Beat below | Status today                                                                                                                                 |
| :- | :-------------------------- | :--------- | :------------------------------------------------------------------------------------------------------------------------------------------- |
| 1  | A review session            | Beat 4     | ✅ built                                                                                                                                     |
| 2  | Your Rust change in action  | Beat 2     | ✅ built                                                                                                                                     |
| 3  | A card synced phone→desktop | Beat 7     | ✅ two-way sync built + tested (`make sync-test`: 20/20, conflict rule). On-device phone→desktop is a manual recording (same engine).        |
| 4  | Three scores with ranges    | Beat 3     | ✅ built (three separate signals + honesty bundle; readiness now emits a real band from practice tests, still give-up-gated)                 |
| 5  | Your AI features            | Beat 8     | ✅ built (off by default): source-traced classifier + generation, gold-eval vs baseline with a pre-set cutoff; app still scores with AI off. |
| 6  | Your test results           | Beat 6     | ✅ built                                                                                                                                     |

## What the app is (say this in Beat 1)

A desktop + mobile study app **forked from Anki** for **one exam: SOA Exam P
(Probability)**. Not a generic flashcard app — it answers three _different_
questions and never blends them:

1. **Memory** — can you recall this fact right now? (Anki's FSRS.)
2. **Performance** — can you solve a _new, exam-style_ question that uses it?
3. **Readiness** — what would you score today, and how sure are we?

The engine change lives in **Anki's Rust core**, not a script on top. SOA Exam P:
computer-based, 3 hours, 30 MCQ (A–E), 5 unscored pilots. Scored 0–10 (0–5 fail,
6–10 pass). Section weights (May 2026): **General Probability 23–30% · Univariate
44–50% · Multivariate 23–30%.** Historical pass rate ~43%.

## Before you record (setup + pre-flight)

Do all of this _before_ hitting record so the video is one clean take.

```bash
# 1. Build + launch the desktop app from source.
cd ~/dev/soap && ./run
#    In the app: File → Import → out/SOA-Exam-P.apkg   (tagged deck; non-destructive)

# 2. Start the phone emulator (leave it booting while you prep desktop).
export ANDROID_HOME="$HOME/Library/Android/sdk"
"$ANDROID_HOME/emulator/emulator" -avd Speedrun_P &
"$ANDROID_HOME/platform-tools/adb" wait-for-device
"$ANDROID_HOME/platform-tools/adb" install -r \
  ~/dev/projects/speedrun/Anki-Android/AnkiDroid/build/outputs/apk/play/debug/AnkiDroid-play-arm64-v8a-debug.apk
```

Pre-flight checklist:

- [ ] `git -C ~/dev/soap log -1 --format='%h %s'` handy (say the commit hash on camera).
- [ ] Deck imported; the app opens on the **custom Home shell** with three tabs — **Concept map · Progress · Readiness** — plus an **"Anki stats"** button (Anki's own screens are restyled to match, and the stock Decks/Add/Browse/Stats toolbar links are removed so it never reads as plain Anki). The standalone **Tools → Exam readiness / Study map** dialogs still open too.
- [ ] Emulator booted to the AnkiDroid deck list (`adb shell getprop sys.boot_completed` → `1`).
- [ ] A terminal open for the `./ninja` / `make` / `unzip` commands.
- [ ] Window layout: app on the left, terminal on the right, emulator ready to bring forward.

## The video script (~4:30, timed)

### Beat 1 — Open: what it is (0:00–0:20)

Say the one-liner and the exam scale (above). _"Three separate signals — Memory,
Performance, Readiness — never blended into one number."_

### Beat 2 — Shot 2: the Rust change in action (0:20–1:05)

In the terminal:

```bash
git -C ~/dev/soap log -1 --format='%h  %s'   # name the commit on camera
./ninja check:rust_test                      # the speedrun engine tests, all green
```

Point at `rslib/src/speedrun/service.rs` and `rslib/src/speedrun/mastery.rs` and
`proto/anki/speedrun.proto`. Say: _"I changed Anki's Rust core — a new
`SpeedrunService` in the `anki` crate: `compute_readiness`, `get_mastery_state`,
`get_mastery_ordered_new_cards`, and `get_points_at_stake_order`, plus two opt-in
live-queue reorders in `build_queues` — wired proto → Rust → Python → web. Not a
wrapper, not a JS reimplementation — a JS/Swift rewrite would cap the grade."_

### Beat 3 — Shot 4: three scores with ranges + the give-up rule (1:05–2:05)

**Tools → Exam readiness (Speedrun).** Point out:

- Three **separate** signals side by side, each with its own status.
- **Syllabus coverage = 0%** even right after importing the whole deck — coverage counts only subtopics you've **actually practiced** (≥1 graded review), weighted by section, so importing a big deck can't fake "covered." It climbs as you study (you'll see this in Beat 4).
- **Graded reviews 0 / 200** → the dashboard stays at **"Not enough data yet."**

Say: _"It refuses to show a readiness number until it has ≥200 graded reviews AND
≥50% weighted coverage — and that's a **Rust assertion**, not a UI hint. The
return type is a `oneof`, so a bare number literally can't be emitted below
threshold."_ Show the honesty bundle: evidence, what's missing, past accuracy, a
**range**, and the single best next action.

Then show the flip side: open the demo collection (`make seed-persona` →
`out/demo-persona.anki2`). With 200+ reviews, 100% coverage, and graded practice
tests, **all three signals now carry a range**: Memory **90% (85–96%)** (mean FSRS
retrievability with a 10th–90th band), and readiness projected **5.5 (4.6–6.4),
P(pass) 14%**, confidence 0.91, next action "focus multivariate." Say: _"This is a
**synthetic demo persona**, labelled as such and reproducible from a seed —
computed by the same code a real student hits, never hardcoded."_

### Beat 4 — Shot 1: a review session on the real engine (2:05–2:45)

Open the **SOA Exam P** deck → study a few cards, grading Again / Hard / Good /
Easy. Reopen the readiness dashboard and show the **graded-review count climbing
and syllabus coverage rising off 0%** as the subtopics you just practiced start to
count — the review loop is running on the real Rust scheduler.

### Beat 5 — The study feature (learning science) (2:45–3:15)

**Tools → Study map (Speedrun).** Exam P at the centre, the 3 units on a triangle,
subtopics radiating out as **bubbles sized by exam weight**. Say: _"This is the
three-tier, mastery-gated scheduler made visible. Bubble size is the topic's exam
weight; the colour fills grey → amber → green as a subtopic clears its gate (≥10
problems, ≥80% accuracy, ≥90% retrievability) and moves from Blocked to
within-unit to cross-unit interleaving. Size is importance, colour is measured
mastery — never blended."_ Tap a subtopic (or a unit) for its mastery detail, and
point out the "Study next" suggestion.

Then name the ablation (in the terminal, optional): `make ablation`. Say: _"The
within-unit tier is the feature I ablate. Three builds — Full, Ablated, Plain —
at **equal study time**; I sweep the assumed effect from **zero**, so at zero the
builds are identical (no built-in bias), and for any positive effect the
pre-registered direction Full ≥ Ablated ≥ Plain holds. Honest: it reports the
null and can't prove the feature without real study logs."_ And the paraphrase
test: `make paraphrase` → _"recall 73% vs reworded 32%, a +41-point gap — proof
Performance isn't just Memory in disguise; a copycat control collapses to zero."_

### Beat 6 — Shot 6: test results (3:15–3:55)

In the terminal:

```bash
./ninja check        # everything green
make bench           # 7h: p50 / p95 / worst per action on a 50k-card deck
make crash-test      # 7g: 20× SIGKILL mid-review, SQLite integrity_check clean every time
```

Say: _"Seeded train/test split, a leakage scan that flags verbatim and near-copy
test items, a one-command benchmark, and a crash test with zero corruption —
anyone can re-run these and get the same numbers."_

### Beat 7 — Shot 3: two-way sync (3:55–4:35)

In the terminal, prove sync end to end on Anki's built-in server:

```bash
make sync-test   # 10 offline reviews on each of two collections -> all 20 land once
```

Say: _"Desktop and phone run the **same compiled Rust engine**, and they sync
through Anki's own protocol. Two collections review 10 different cards each
offline, then sync — all 20 land once, none lost or doubled; a same-card conflict
keeps both reviews and picks a deterministic winner (`docs/sync-conflict-rule.md`)."_
Then bring the emulator forward — AnkiDroid on **our** backend — and prove the
engine is ours (see "Prove the engine is yours" below).

**Final-cut TODO:** record the on-device version (review on the phone → sync →
appears on desktop). The scripted test exercises the identical sync code path
because the phone runs this same engine; the phone recording is the last capture.

### Beat 8 — Shot 5: AI features, checked, and still scores with AI off (4:35–close)

In the terminal:

```bash
make ai-eval     # classifier + generation evals vs their baselines, on held-out gold
```

Say: _"AI is **off by default** — you just saw all three signals compute without
it. The AI features are source-traced: every generated card carries its named
source and is quarantined `ai::unreviewed` until a human approves it, and every
call is logged. Each feature is checked on a held-out gold set against a simpler
baseline with a **pre-registered cutoff**."_ Show the measured PASS: on the
official SOA corpus (leakage-clean), **classifier** AI top-1 **38%** vs keyword
**13%** (+25 pts), **generation** AI **92%** correct / **0%** bad-teaching vs the
**24%** extraction baseline — both clear the pre-set cutoff (`docs/ai-results.md`).

(The AI rows appear when `OPENAI_API_KEY` is set — put it in a gitignored `.env`;
the Makefile auto-loads it. Without a key the baselines still print and the app
still scores with AI off.)

## Run it on the phone emulator (exact commands)

An AVD named **`Speedrun_P`** (arm64) already exists.

```bash
export ANDROID_HOME="$HOME/Library/Android/sdk"

# Boot the emulator (drop -no-window if you want it headless for CI).
"$ANDROID_HOME/emulator/emulator" -avd Speedrun_P &
"$ANDROID_HOME/platform-tools/adb" wait-for-device
"$ANDROID_HOME/platform-tools/adb" shell getprop sys.boot_completed   # wait until this prints 1

# Install our APK (built from our fork's engine).
"$ANDROID_HOME/platform-tools/adb" install -r \
  ~/dev/projects/speedrun/Anki-Android/AnkiDroid/build/outputs/apk/play/debug/AnkiDroid-play-arm64-v8a-debug.apk
```

Then open AnkiDroid on the emulator; load the Exam P deck (export a `.colpkg` from
desktop, or sync once that's wired) and run a review — it exercises the same
scheduler/engine as desktop. To (re)build the APK from scratch, see
`docs/android-build.md`.

## Prove the engine is yours ("show they're mine")

Strongest → simplest. Any one of these is convincing; do the first on camera.

1. **The speedrun engine is compiled into the phone binary.** The stripped `.so`
   still carries our source paths, the compiled proto, and our request types:

```bash
export LC_ALL=C
APK=~/dev/projects/speedrun/Anki-Android/AnkiDroid/build/outputs/apk/play/debug/AnkiDroid-play-arm64-v8a-debug.apk
unzip -p "$APK" lib/arm64-v8a/librsdroid.so | strings | grep -iE "speedrun|ComputeReadiness|Mastery" | head
# → anki/rslib/src/speedrun/service.rs
#   anki/rslib/src/speedrun/mastery.rs
#   .../out/anki.speedrun.rs        (our compiled protobuf)
#   ComputeReadinessRequest, MasteryRequest, ...
```

This is the money shot: it proves it's the **SOA-P speedrun engine**, not just
"an Anki engine."

2. **The `librsdroid.so` is present and is our compiled Rust backend:**

```bash
unzip -l "$APK" | grep librsdroid.so     # lib/arm64-v8a/librsdroid.so (~48 MB)
```

3. **Provenance:** the backend's `anki` submodule is repointed at this fork
   (`git checkout fork/main`), so the engine that cross-compiles into the `.so`
   _is_ this repo. See `docs/android-build.md`.

4. **On-device load (optional):** while reviewing, `adb logcat | grep -i backend`
   shows AnkiDroid loading our native backend (`makeBackendUsable` succeeds).

Desktop side: the identical `anki` crate is what `./ninja check:rust_test`
exercises on the desktop — one engine, two platforms.

## The separate-device / clean-machine download

This covers the **"either app fails on a clean device → 50% max"** hard limit.
"Clean" = a device **without** the dev toolchain (no Rust/Node/Python). Record
each install running end to end.

**Desktop (macOS DMG) — no second Mac needed.** The app is **self-contained**: it
bundles its own `Python.framework`, and the binary links only macOS system
frameworks + that bundled runtime (verified with `otool -L` — no Rust/Node/Homebrew/
repo paths). So "clean" just means _without your dev toolchain or source tree_:

```bash
ls -lh out/installer/dist/anki-25.09.99-mac-apple.dmg   # ~218 MB drag-install DMG
```

- **Fresh user account (fastest, zero download).** System Settings → Users & Groups
  → add a **Standard** user. Mount the DMG, drag **Anki.app** onto **Applications**
  (shared across users). Log into the new account and launch Anki (first launch:
  right-click → **Open**, it's unsigned). That account has none of your PATH / cargo /
  node / repo, so a clean launch there shows it runs standalone.
- **Throwaway macOS VM (most airtight; needs ~40 GB free — currently only ~18 GB).**
  Free space first, then `brew install cirruslabs/cli/tart` →
  `tart clone ghcr.io/cirruslabs/macos-sequoia-base:latest clean && tart run clean`
  → install the DMG inside. Or rent a cloud Mac (AWS EC2 mac, MacStadium) for an hour.
- **Prove no hidden dependency (add to any recording):**
  `otool -L /Applications/Anki.app/Contents/MacOS/Anki` (system + bundled Python
  only) · temporarily `mv ~/dev/soap /tmp/soap.hidden` and relaunch the installed
  app · or `env -i /Applications/Anki.app/Contents/MacOS/Anki` to launch with an
  empty environment.

Either route: **Apple Silicon only** (the binary is arm64). Confirm it opens a
collection and **Tools → Exam readiness / Study map** work — i.e. it runs standalone.

**Phone (Android APK):**

- Same-machine emulator: `adb install -r <the APK path above>` (as in setup).
- A real/clean phone: transfer the APK and sideload (enable "Install unknown
  apps"), **or** `adb install -r` over USB. Then run a review session.

**Both must run with AI switched OFF and still give a score** — which they do (AI
is off by default; `test_three_signals_compute_with_ai_off`). Say that explicitly
on camera.

## What's built vs planned (be honest on camera)

- **Built:** real Rust engine change (7 RPCs); three separate signals; give-up
  rule (Rust `oneof` assertion + test); **readiness band from graded practice
  tests** (Wilson interval + P(pass), still give-up-gated); mastery model + tier
  ordering **wired into the live queue** (opt-in `speedrunMasteryScheduler`);
  points-at-stake review order (`GetPointsAtStakeOrder` + opt-in
  `speedrunPointsAtStake`); importance-weighted mastery rollup + "what to study
  next"; importance-sized **bubble** study map; readiness dashboard + honesty
  bundle; FSRS memory-calibration harness (`make calibration`); **performance
  model** on a held-out item corpus × synthetic cohort (`make performance
  ARGS="--persona"`); **practice-test mode** + a seeded **synthetic demo persona**
  (`make seed-persona`) that makes the three scores show real, reproducible, clearly
  labelled numbers; **AI layer off by default** (source-traced classifier +
  generation, gold evals vs baselines with pre-set cutoffs, audit log,
  `ai::unreviewed` quarantine); **two-way sync tested** (`make sync-test`) +
  conflict rule; syllabus taxonomy + weights + 42-card tagged deck; weighted
  coverage; **shared engine on the phone**; seeded split + leakage scan + benchmark
  - crash test; desktop DMG + phone APK.
    Also built since: **paraphrase test** (`make paraphrase`, 7d — recall 73% vs
    reworded 32%, +41-pt gap); **3-build ablation run** (`make ablation` — equal
    study time, null included, direction holds); **live AI-vs-baseline numbers**
    (`make ai-eval` with a key — classifier +25 pts, generation 92% vs 24%, both
    PASS).
- **Planned (Sunday — `docs/vision.md`):** the on-device phone↔desktop sync
  recording; a native AnkiDroid score screen (`docs/phone-scores.md`); fusing the
  per-question performance model into readiness; validation against real students.

## Feature reference (one line each, for Q&A)

1. **Real Rust engine change** — `SpeedrunService` in the `anki` crate, proto → Rust → Python → web. `rslib/src/speedrun/`.
2. **Three separate scores, never blended** — Memory / Performance / Readiness side by side.
3. **Honesty + give-up rule** — no readiness number below ≥200 reviews AND ≥50% weighted coverage; enforced as a Rust `oneof`.
4. **Three-tier, mastery-gated scheduler** — per-subtopic gate from revlog accuracy + FSRS retrievability; `rslib/src/speedrun/mastery.rs`.
5. **Study map** — importance-sized bubble concept map (bubble size = exam weight, colour = measured mastery) + "what to study next"; `ts/routes/study-map`.
6. **Readiness dashboard** — three signals + full honesty bundle; `ts/routes/readiness-dashboard`.
7. **Syllabus taxonomy + tagged deck** — 3 units, 19 subtopics from the 2026-05 outcomes; `pylib/anki/speedrun/exam_p_topics.json`, `out/SOA-Exam-P.apkg`.
8. **Weighted coverage** — coverage weighted by official section weights.
9. **Shared engine on the phone** — AnkiDroid APK built from our `librsdroid.so`; `docs/android-build.md`.
10. **Reproducibility** — seeded split, leakage scan, `make bench`, `make crash-test`; `tools/speedrun/`.

## Key files (for Q&A)

- Engine: `rslib/src/speedrun/{service.rs,mastery.rs}`, `proto/anki/speedrun.proto`
- Give-up rule test: `pylib/tests/test_speedrun.py`
- Taxonomy + deck: `pylib/anki/speedrun/{exam_p_topics.json,seed.py}`
- UI: `ts/routes/{readiness-dashboard,study-map}/+page.svelte`
- Phone: `docs/android-build.md`
- Vision + AI plan: `docs/vision.md`, `docs/ai-features-prd.md`
