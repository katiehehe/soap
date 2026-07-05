# Upstream files touched (merge-difficulty log)

Tracks every **upstream Anki** file this fork modifies, so rebasing on new Anki
releases stays predictable. New files added by the fork carry no merge risk and
are listed separately. Keep this in sync with `SPEC_CHECKLIST.md`.

Format: `path - what changed - merge risk (low/med/high)`.

## Upstream files modified

- `rslib/src/lib.rs` - add `pub mod speedrun;` (1 line) - low. Isolated module
  declaration; conflicts only if upstream edits adjacent lines.
- `rslib/proto/src/lib.rs` - add `protobuf!(speedrun, "speedrun");` (1 line) - low.
  Registers the new prost module.
- `rslib/proto/python.rs` - add `import anki.speedrun_pb2` to the generated-header
  import list (1 line) - low/med. This hardcoded list is the one place new proto
  packages must be registered for the Python backend; rarely edited upstream.
- `qt/aqt/mediasrv.py` - add `"readiness-dashboard"`, `"study-map"`, `"metrics"`
  and `"formula-sheet"` to `is_sveltekit_page()`, and `"compute_readiness"` + `"get_mastery_state"` +
  `"get_study_plan"` + `"get_study_pace"` to `exposed_backend_list` (6 entries)
  - med. Also add `"/_anki/computeReadiness"`, `"/_anki/getMasteryState"`,
    `"/_anki/getStudyPlan"` and `"/_anki/getStudyPace"` to the request allow-list
    in `_check_dynamic_request_permissions()` so the read-only speedrun endpoints
    have a deterministic authorization path independent of the webview's
    `Authorization` header injection (4 entries) - med. Plus `"/_anki/graphs"`,
    `"/_anki/getGraphPreferences"` and `"/_anki/setGraphPreferences"` (3 entries),
    because the Home shell's Stats tab inlines Anki's own review-history graphs
    and renders in the MAIN webview (no header path), so without them the Stats
    tab always 403s ("Unexpected API access"); all three touch only the user's
    local review history / graph display prefs. All append-only additions.
- `qt/aqt/main.py` - the custom app shell + hooks - med, append-only:
  (1) add `"speedrunHome"` to the `MainWindowState` union and make it the app's
  landing state (`moveToState("speedrunHome")`), with `_speedrunHomeState()` /
  `_speedrunHomeCleanup()` rendering the SvelteKit `home` shell into `mw.web`;
  (2) two Tools-menu `QAction`s (`Exam readiness`, `Study map`) + their handlers;
  (3) startup calls `aqt.speedrun.register_reviewer_banner()` (review-time tier
  banner), `register_collection_hooks()` (first-run deck seed), and
  `register_theme()` (app-wide accent + restyle of Anki's own screens).
- `qt/aqt/webview.py` - add `SPEEDRUN` to the `AnkiWebViewKind` enum and include it
  in the API-access list in `AnkiWebPage._profileForPage()` (2 entries) - med. Both
  append-only; without this the speedrun pages get "Unexpected API access"/403.
- `qt/aqt/toolbar.py` - replace the stock center links (Decks/Add/Browse/Stats)
  in `_centerLinks()` with the custom shell's `Home` + `Study next` + `Sync`, so
  Anki's own screens don't read as stock Anki (the Decks/Add/Browse/Stats flows
  live in the custom Home top bar instead) - med. The handler methods
  (`_speedrun_home_handler`, `_speedrun_study_recommended_handler`) are
  append-only; the change to the links list is a replacement, so re-check on a
  future rebase if upstream restructures `_centerLinks`.
- `rslib/src/scheduler/queue/builder/mod.rs` - in `Collection::build_queues`,
  after `gather_cards`, four small opt-in hooks: when `speedrunMasteryScheduler`
  is on, (a) STRICT-TIER SCOPE the gathered new + review cards to the tier deck
  being studied (`speedrun_scope_queues_to_tier`), then (b) reorder the new cards
  by mastery tier AND (c) reorder the due review cards by the same tier (so
  blocked practice carries through reviews until a subtopic clears); when
  `speedrunPointsAtStake` is on, reorder the due review cards by points-at-stake
  (topic weight x weakness). The strict-tier scope reads a transient
  `speedrunActiveTierScope` config (`{deck_id, tier}`, keyed to the deck being
  studied), so opening a unit deck (within-unit tier) or the root deck
  (cross-unit tier) serves ONLY the subtopics actually in that mastery pool — a
  still-Blocked subtopic can no longer leak in via the parent deck's subtree. It
  only DROPS out-of-tier gathered cards (like a per-deck limit); cards with no
  syllabus subtopic are never touched. All flags default off; when both reorder
  flags are on the tier reorder runs after points-at-stake, so the tier is
  primary and stakes break ties within a tier. The hooks live in
  `rslib/src/speedrun/mastery.rs` (`speedrun_scope_queues_to_tier`,
  `speedrun_reorder_new_cards`, `speedrun_reorder_review_cards`,
  `speedrun_reorder_review_cards_by_tier`), are read-only (no writes, so
  undo/integrity and FSRS intervals are untouched), and the flags use plain
  string config keys so upstream's `BoolKey` enum is not modified. With the flags
  off (and no scope config) the queue is built exactly as upstream.
- `ts/routes/base.scss` - add the Speedrun theme tokens at `:root` and scope the
  surface/text remap to the speedrun roots (`.app`, `.readiness`, `.study-map`,
  `.congrats`, `.metrics`, `.formula-sheet`, `.ptest`). Currently the **SOAP**
  "clean/fresh" DNA: aqua/teal palette (light porcelain hero + dark bath-water),
  Fredoka/Nunito fonts, bubbly radii, foam shadows; the fixed signal colours stay
  semantic. Stock Anki screens never carry these classes - low/med.
- `ts/routes/+layout.svelte` - swap the self-hosted Fontsource imports to the SOAP
  pair (Fredoka + Nunito, replacing Fraunces + DM Sans); referenced only via the
  `--sr-font-*` tokens, so stock Anki screens keep their own fonts (2 lines) - low.
- `ts/routes/graphs/graphs-base.scss` - reskin Anki's Stats page (Inter font +
  app-accent on each graph card's title bar); graph DATA colours untouched, so
  the stats stay legible - low.
- `ts/routes/congrats/CongratsPage.svelte` - restyle the end-of-review congrats
  screen as a custom accent card: the **SOAP** wordmark + soap BrandMark, a
  "Squeaky clean!" kicker, and decorative rising soap bubbles (reduced-motion
  gated); plus two navigation buttons shown when `bridgeCommandsSupported`:
  "Study next" (pycmd
  `speedrun-study-next` -> `study_recommended`, opens the next due deck) and "Back
  to plan" (pycmd `speedrun-plan` -> home shell on the Plan tab). Both handled in
  `aqt/speedrun.py`'s `_on_js_message` hook (append-only) - low.
- `qt/aqt/progress.py` - crash fix - low, append-only. `ProgressManager._set_busy_cursor`
  skips the themed wait cursor on macOS (realizing it runs `QImage::toCGImage` ->
  `CGImageCreate`, which SIGTRAPs the whole app with a pointer-authentication trap on
  recent macOS, killing any slow op such as sync/sign-in), and `_restore_cursor` now only
  pops a cursor we actually pushed (tracked by a new `_busy_cursor_active` flag), which
  also fixes a latent override-cursor stack underflow when an op finishes under 300ms.
  Isolated to two small methods + one init field; low rebase risk.
- `pylib/tests/{test_collection,test_importing,test_models,test_schedv3,test_stats}.py`
  - unused-import cleanups only (e.g. dropping unused `pytest`/`re`/`os` imports);
    no behaviour change - low.

Note: `get_study_plan` also _reads_ `Collection::deck_tree` (an existing public
method) to get Anki's own daily-limit-capped due counts, and `get_study_pace`
_reads_ the revlog (first graded review = start of the study history) for the
mastery pace. Both are reads, not
modifications of upstream code, so they add no merge surface. The "Study more
today" button calls the existing `Scheduler.extend_limits` from
`qt/aqt/speedrun.py` (no upstream edit).

## New files added by the fork (no merge risk)

- `proto/anki/speedrun.proto` - `SpeedrunService` (7 RPCs: `SpeedrunPing`,
  `ComputeReadiness`, `GetMasteryState`, `GetMasteryOrderedNewCards`,
  `GetPointsAtStakeOrder`, `GetStudyPlan`, `GetStudyPace`).
- `rslib/src/speedrun/mod.rs`, `rslib/src/speedrun/service.rs` - service impl + tests.
- `qt/aqt/speedrun.py` - the readiness dashboard + study map dialogs (host the pages).
- `ts/routes/readiness-dashboard/+page.svelte` - dashboard (three signals + honesty).
- `ts/routes/study-map/*` - the importance-sized bubble concept map (bubble size =
  exam weight, colour = measured mastery) + geometry lib/tests; calls
  `get_mastery_state`, `get_study_plan` (the "Today's plan" tiered deck list),
  and `get_study_pace` (the "Mastery pace" card).
- `pylib/anki/speedrun/__init__.py`, `.../exam_p_topics.json`, `.../seed.py` - topic map
  (official 2026-05 outline), tag helpers, and the tagged deck builder.
- `tools/speedrun/build_exam_p_deck.py` - CLI to seed the deck / export an importable `.apkg`.
- `pylib/tests/test_speedrun.py`, `pylib/tests/test_speedrun_deck.py` - Python tests.
- `ts/tests/e2e/readiness-dashboard.test.ts`, `ts/tests/e2e/study-map.test.ts` - Playwright
  tests + screenshots.
- `docs/rust-change.md`, `docs/upstream-touched.md`, `docs/vision.md` - documentation.
- Later fork-owned additions (no merge surface): `pylib/anki/speedrun/{persona.py,
  practice_test.py,performance.py,calibration.py,evalsplit.py,soa_sample.py,
  sample_items.json,ai.py,gen_sources.json,paraphrase.py,paraphrase_items.json,
  ablation.py}`; `tools/speedrun/evals/*` (classify/generate/performance/paraphrase/
  ablation/practice-test/memory-calibration) + `tools/speedrun/{bench,crash_test,
  leakage_scan,sync_test,seed_persona}.py`; `ts/routes/home/*` (the custom shell);
  `ts/routes/speedrun-ui/*` (shared Button + BrandMark soap mark + signal colours);
  `Makefile`; docs `{score-models,ai-results,paraphrase-test,study-feature-ablation,
  latency,recording-steps,brainlift,demo-script,sync-conflict-rule,android-build}.md`.
  See `SPEC_CHECKLIST.md` for the authoritative running list.

## Generated (not committed; produced by the build into `out/`)

- `out/pylib/anki/_backend_generated.py`, `out/pylib/anki/speedrun_pb2.py`
- `out/ts/lib/generated/backend.ts`, `out/ts/lib/generated/anki/speedrun_pb.ts`
- proto descriptors

## Mobile (separate repos, not part of this repo's merge surface)

- `Anki-Android` and `Anki-Android-Backend` are cloned as siblings under
  `~/dev/projects/speedrun/` (next to `soap`). To ship OUR engine to the phone,
  point `Anki-Android-Backend/anki` (a submodule) at this fork, then rebuild the
  `.aar`. Toolchain installed: NDK `29.0.14206865`, SDK command-line tools; AVD
  `Speedrun_P` exists for the emulator run (`make phone`). NOTE: the backend
  submodule's `anki` `fork` remote still points at the pre-move path
  `/Users/katiehe/dev/soap`; repoint it to `…/dev/projects/speedrun/soap` before
  `make phone-rebuild` so the phone can build from the current engine commit
  (today's APK is pinned at engine `f876127df`).
