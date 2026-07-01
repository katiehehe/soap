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
- `qt/aqt/mediasrv.py` - add `"readiness-dashboard"` to `is_sveltekit_page()` and
  `"compute_readiness"` to `exposed_backend_list` (2 entries) - med. Both are
  append-only additions to upstream lists.
- `qt/aqt/main.py` - add a Tools-menu `QAction` in `setupMenus()` plus an
  `on_speedrun_readiness()` method (2 small insertions) - med.

## New files added by the fork (no merge risk)

- `proto/anki/speedrun.proto` - `SpeedrunService` (`SpeedrunPing`, `ComputeReadiness`).
- `rslib/src/speedrun/mod.rs`, `rslib/src/speedrun/service.rs` - service impl + tests.
- `qt/aqt/speedrun.py` - the readiness dashboard dialog (hosts the SvelteKit page).
- `ts/routes/readiness-dashboard/+page.svelte` - dashboard stub (give-up + honesty layout).
- `pylib/anki/speedrun/__init__.py`, `.../exam_p_topics.json`, `.../seed.py` - topic map,
  tag helpers, and the tagged deck builder.
- `tools/speedrun/build_exam_p_deck.py` - CLI to seed the deck into a collection.
- `pylib/tests/test_speedrun.py`, `pylib/tests/test_speedrun_deck.py` - Python tests.
- `ts/tests/e2e/readiness-dashboard.test.ts` - Playwright test + screenshot.
- `docs/rust-change.md`, `docs/upstream-touched.md` - documentation.

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
