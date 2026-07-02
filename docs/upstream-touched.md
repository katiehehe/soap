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
- `qt/aqt/mediasrv.py` - add `"readiness-dashboard"` and `"study-map"` to
  `is_sveltekit_page()`, and `"compute_readiness"` + `"get_mastery_state"` to
  `exposed_backend_list` (4 entries) - med. Also add `"/_anki/computeReadiness"`
  and `"/_anki/getMasteryState"` to the request allow-list in
  `_check_dynamic_request_permissions()` so the two read-only speedrun endpoints
  have a deterministic authorization path independent of the webview's
  `Authorization` header injection (2 entries) - med. All append-only additions.
- `qt/aqt/main.py` - add two Tools-menu `QAction`s in `setupMenus()`
  (`Exam readiness`, `Study map`) plus `on_speedrun_readiness()` and
  `on_speedrun_study_map()` methods, and one `aqt.speedrun.register_reviewer_banner()`
  call in `setupMenus()` to register the review-time mastery-tier banner hooks - med.
  All append-only.
- `qt/aqt/webview.py` - add `SPEEDRUN` to the `AnkiWebViewKind` enum and include it
  in the API-access list in `AnkiWebPage._profileForPage()` (2 entries) - med. Both
  append-only; without this the speedrun pages get "Unexpected API access"/403.
- `qt/aqt/toolbar.py` - add two center links (`Readiness`, `Study map`) in
  `_centerLinks()` plus `_speedrun_readiness_handler()` /
  `_speedrun_study_map_handler()` methods, so the pages are first-class toolbar
  buttons, not only Tools-menu items - med. Append-only additions.
- `rslib/src/scheduler/queue/builder/mod.rs` - in `Collection::build_queues`,
  after `gather_cards`, two small opt-in hooks: reorder the gathered new cards by
  mastery tier when `speedrunMasteryScheduler` is on, and reorder the due review
  cards by points-at-stake (topic weight x weakness) when `speedrunPointsAtStake`
  is on (both default off) - low/med. The reorders live in
  `rslib/src/speedrun/mastery.rs` (`speedrun_reorder_new_cards`,
  `speedrun_reorder_review_cards`), are read-only (no writes, so undo/integrity
  and FSRS intervals are untouched), and the flags use plain string config keys
  so upstream's `BoolKey` enum is not modified. With the flags off the queue is
  built exactly as upstream.

## New files added by the fork (no merge risk)

- `proto/anki/speedrun.proto` - `SpeedrunService` (5 RPCs: `SpeedrunPing`,
  `ComputeReadiness`, `GetMasteryState`, `GetMasteryOrderedNewCards`,
  `GetPointsAtStakeOrder`).
- `rslib/src/speedrun/mod.rs`, `rslib/src/speedrun/service.rs` - service impl + tests.
- `qt/aqt/speedrun.py` - the readiness dashboard + study map dialogs (host the pages).
- `ts/routes/readiness-dashboard/+page.svelte` - dashboard (three signals + honesty).
- `ts/routes/study-map/*` - the importance-sized bubble concept map (bubble size =
  exam weight, colour = measured mastery) + geometry lib/tests; calls
  `get_mastery_state`.
- `pylib/anki/speedrun/__init__.py`, `.../exam_p_topics.json`, `.../seed.py` - topic map
  (official 2026-05 outline), tag helpers, and the tagged deck builder.
- `tools/speedrun/build_exam_p_deck.py` - CLI to seed the deck / export an importable `.apkg`.
- `pylib/tests/test_speedrun.py`, `pylib/tests/test_speedrun_deck.py` - Python tests.
- `ts/tests/e2e/readiness-dashboard.test.ts`, `ts/tests/e2e/study-map.test.ts` - Playwright
  tests + screenshots.
- `docs/rust-change.md`, `docs/upstream-touched.md`, `docs/vision.md` - documentation.

## Generated (not committed; produced by the build into `out/`)

- `out/pylib/anki/_backend_generated.py`, `out/pylib/anki/speedrun_pb2.py`
- `out/ts/lib/generated/backend.ts`, `out/ts/lib/generated/anki/speedrun_pb.ts`
- proto descriptors

## Mobile (separate repos, not part of this repo's merge surface)

- `Anki-Android` and `Anki-Android-Backend` are cloned as siblings under `~/dev/`.
  To ship OUR engine to the phone, point `Anki-Android-Backend/anki` (a submodule
  currently pinned to upstream) at this fork, then rebuild the `.aar`. Toolchain
  installed: NDK `29.0.14206865`, SDK command-line tools; AVD `Medium_Phone` exists
  for the emulator run.
