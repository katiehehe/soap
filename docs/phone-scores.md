# The three scores on the phone (Friday, mobile)

The Friday mobile item asks that the phone "shows the three scores with ranges and
follows the give-up rule." Here is the honest status and how to verify it.

## The scoring lives in the shared engine, not the UI

All three signals are computed by the **Rust engine** that ships to both desktop
and phone (`rslib/src/speedrun/`), behind one give-up rule:

- `compute_readiness` returns `oneof { NoScore, ReadinessScore }`: a bare number
  literally cannot be emitted below threshold, on **either** platform.
- `get_mastery_state` (the measured mastery signal) and the FSRS memory signal are
  the same code on both.

The AnkiDroid build is compiled from **our** engine, so these RPCs are present in
the on-device binary. Proof (from `docs/demo-script.md`):

```bash
APK=~/dev/projects/speedrun/Anki-Android/AnkiDroid/build/outputs/apk/play/debug/AnkiDroid-play-arm64-v8a-debug.apk
unzip -p "$APK" lib/arm64-v8a/librsdroid.so | strings | grep -iE "ComputeReadiness|Mastery|speedrun"
# -> anki/rslib/src/speedrun/service.rs, ComputeReadinessRequest, MasteryRequest, ...
```

Because desktop and phone share one collection via sync, once the phone syncs the
demo-persona collection (`make seed-persona`, then sync), `compute_readiness` on
the phone returns the **same** honesty-bundled band the desktop shows, using the
same engine, same inputs, same number.

## What is built: the SAME UI build on the phone (WebView parity)

The phone renders the **exact same Svelte UI build** as the desktop, not a
re-implementation. AnkiDroid renders Anki's Svelte "pages" in a WebView
(`com.ichi2.anki.pages.PageFragment`), and our whole sveltekit app (including
every custom route) is bundled into the engine `.aar` and packaged in the APK
(`assets/backend/sveltekit`; verified: all 19 route chunks present, including the
new `formula-sheet`/`metrics`/`practice-test`/`add-card`).

**The app now launches straight into the Svelte `home` shell**, the phone analog
of the desktop `moveToState("speedrunHome")`. `home` is a single-webview tabbed
SPA, so one WebView surfaces every sub-screen as an in-page tab (Map, Plan,
Memory, Formulas, Readiness, Stats, How it works), matching the desktop
`speedrunHome` window. The native deck browser stays reachable underneath (Home →
Decks chip, and the nav drawer's Home/Decks items), exactly as the desktop keeps
its deck browser.

Two channels reach the shared engine, identical to desktop:

- **`@generated/backend` RPCs** (`computeReadiness` / `getMasteryState` /
  `getStudyPlan` / `getStudyPace`) flow through AnkiDroid's nanohttpd POST bridge
  (`PostRequestHandler.collectionMethods`). Unlike desktop Qt (`qt/aqt/mediasrv.py`
  auto-proxies the whole backend list), AnkiDroid dispatches through an explicit
  allowlist, so each RPC is registered there → `backend.<name>Raw(bytes)`. No
  scoring on the client.
- **`window.bridgeCommand("speedrun-*", cb)`**: handled by a new
  `SpeedrunPageFragment` base that mirrors the desktop `qt/aqt/speedrun.py`
  handlers in Kotlin. AnkiDroid's stock `PageFragment` bridge is void + exact-match
  only and can't return a value to a callback, so `SpeedrunPageFragment` injects a
  callback-capable `window.bridgeCommand` (synchronous `@JavascriptInterface`
  returning JSON) that dispatches config writes, deck opening, settings, and the
  formula-sheet/add-card reads on the SHARED collection (which syncs to desktop).

### Files (in the AnkiDroid clone, `Anki-Android/`)

Not part of this repo's git; they live in the sibling AnkiDroid checkout that
consumes our engine `.aar` (see `docs/android-build.md`):

- **`pages/SpeedrunPageFragment.kt` (new)** is the base class: the callback-capable
  `speedrun-*` bridge (settings, set-theme, set-scheduler/guided/ai/exam-date/unlock,
  nav:browse/decks/sync/stats/study, study/study-unit/study-all/study-deck,
  formula-cards, add-card). Practice-test assemble/grade + AI classify return an
  empty result (see gaps below).
- **`pages/HomePage.kt` (new)**: `SpeedrunPageFragment(pagePath="home")`,
  full-bleed (`res/layout/fragment_speedrun_home.xml`, no Anki toolbar). The
  landing screen.
- **`pages/StudyMapPage.kt`, `PracticeTestPage.kt`, `FormulaSheetPage.kt`,
  `MetricsPage.kt` (new)**: standalone entry points / deep links for each route
  (also reached as tabs inside `home`).
- `pages/ReadinessDashboardPage.kt` is unchanged (still a `PageFragment`).
- **`DeckPicker.kt`**: on a normal launcher start (`ACTION_MAIN`, fresh create) it
  now `startActivity(HomePage.getIntent(this))`; guarded so review/import/sync
  flows are untouched.
- **`pages/PageWebViewClient.kt`**: `isSvelteKitPage` allowlist extended with
  `practice-test`, `formula-sheet`, `metrics`, `add-card` (mirrors the desktop
  `is_sveltekit_page`).
- **`NavigationDrawerActivity.kt` + `res/menu/navigation_drawer.xml`**: added a
  **Home** drawer entry → `HomePage`.
- `pages/PostRequestHandler.kt`: the SpeedrunService RPCs were already registered.
- **Deleted:** `ReadinessScoresActivity.kt` + `res/layout/activity_readiness_scores.xml`
  + its `AndroidManifest.xml` entry. That native Kotlin screen re-drew the scores
  outside the WebView; readiness now stays engine-sourced via the Svelte route
  (honesty rule).
- `gradle/libs.versions.toml`: `ankiBackend` bumped `0.1.64-anki25.09.2` →
  `0.1.65-anki26.05b1` (matches the local backend `VERSION_NAME`, so a non-local
  build can't silently pull stock upstream Anki).

### How it was verified (emulator `Speedrun_P`, arm64)

- Rebuilt the local AAR (`cargo run -p build_rust`): `librsdroid.so` carries our
  engine (`ComputeReadinessRequest`, `speedrunMasteryScheduler`, …) and the fresh
  sveltekit bundle includes all routes.
- `./gradlew :AnkiDroid:assemblePlayDebug` **succeeds**; the new Kotlin compiles
  clean; installed the arm64 APK.
- On launch the app opens the **Svelte `home` shell full-bleed** (logcat:
  `PageFragment: Loading http://127.0.0.1:PORT/home`,
  `SingleFragmentActivity::HomePage::onResume`, `ResumedActivity=…SingleFragmentActivity`,
  no `FATAL`). The Map/Readiness/How-it-works/Formulas tabs all render and their
  engine calls fire (  `AnkiServer: POST /_anki/{getMasteryState,computeReadiness,
  getStudyPlan,getStudyPace}`). Readiness shows the three separate signals with the
  honest abstain state; "How it works" shows the give-up rule "enforced in Rust".
- **Populated three-scores capture (this session, `Speedrun_P`):** after the
  fully-scored synthetic-persona collection was on the phone, the Svelte
  `readiness-dashboard` route rendered all three signals **with ranges**,
  engine-computed on-device (`POST /_anki/computeReadiness` in logcat):
  - **Memory** `89% (82%-96%)` · "137 cards reviewed · 10th-90th pct range"
    (`out/phone-3scores-memory.png`)
  - **Performance** `Not yet measured · needs exam-style items`, the honest
    give-up state (`out/phone-3scores-performance.png`)
  - **Readiness** `5.5 (4.6-6.4)` · `SCORE AVAILABLE` · Coverage 100% · confidence
    0.91 · P(pass today) 14% · single best next action
    (`out/phone-3scores-readiness.png`)
  The coloured study map renders the same data (`out/phone-studymap.png`). This is
  the identical `oneof {NoScore, ReadinessScore}` the desktop shows, using the same engine,
  same inputs, same numbers (verified: `compute_readiness` on the on-device
  collection returns `5.5 (4.6-6.4)`), never a bare or fabricated number.

**Engine version note (reconciliation):** the currently-built APK bundles engine
`0.1.65-anki26.05b1` at commit **`f876127df`** (logcat: `Backend Version = …
f876127df…`). The desktop repo has since advanced its `rslib/src/speedrun/`
mastery + service code and `proto/anki/speedrun.proto` (a large refactor), so the
phone's `getMasteryState`/readiness use the **older** RPC signature. All three
scores still render correctly under the give-up rule; the only visible difference
is that the phone's **Performance** card abstains ("Not yet measured") where the
newer desktop engine surfaces a per-subtopic performance number. To bring the
phone fully level with desktop, rebuild the APK from current HEAD with
`make phone-rebuild`, but first repoint the backend submodule's `fork` remote,
which still points at the pre-move path `/Users/katiehe/dev/soap` (the repo now
lives at `…/dev/projects/speedrun/soap`), or `phone-rebuild` can only overlay
uncommitted working-tree files onto the `f876127df` base.

## Light/dark theme (parity with desktop)

The Speedrun UI's light/dark palette is driven by **one shared contract**: a
`night-mode` class on the WebView's `<html>` element (`ts/routes/base.scss` +
`ts/lib/sass/_root-vars.scss`, read via `ts/lib/tslib/nightmode.ts`). Both
platforms feed that same class, so the phone matches the desktop with no
platform-specific theme code in Svelte:

- **Initial theme (already worked):** AnkiDroid's `PageFragment` appends `#night`
  to the page URL when `Themes.isNightTheme` (stock upstream behaviour), and
  `checkNightMode()` turns that into the `night-mode` class, exactly like the
  desktop `load_sveltekit_page` (`qt/aqt/webview.py`). Because `AnkiActivity`
  resolves the theme in `onCreate` before the fragment loads, the home shell
  opens in the correct mode for the current Android day/night setting. `targetSdk
  35` means WebView algorithmic darkening defaults **off** and honours the page's
  CSS `color-scheme`, so there is no double-darkening.
- **The in-app Light/Dark toggle (the bug that was fixed):** the home settings
  strip sends `speedrun-set-theme:dark|light`. On desktop this calls
  `mw.set_theme(...)` and the `theme_did_change` hook flips the `night-mode` class
  live. On the phone this command was a **no-op**, so the toggle did nothing.
  That was the "light and dark mode didn't work on android" report.
  `SpeedrunPageFragment.setTheme(...)` now (a) persists `Prefs.appTheme` =
  `NIGHT`/`DAY` (so it sticks and native screens opened afterwards adopt it), and
  (b) toggles the `night-mode` class in the WebView live via `evaluateJavascript`
  (mirroring the desktop hook) + re-tints the status bar, with no reload, so the
  current tab / in-progress test are preserved.

Verify on the emulator: open the home shell, expand **Settings**, tap
**Light**/**Dark**: the whole Speedrun UI recolours instantly and the choice
survives an app restart. Toggling Android's own day/night (or AnkiDroid Settings →
Appearance) and reopening the app also lands in the right mode.

## Known gaps (Python-only, need a shared-engine RPC)

A few desktop `speedrun-*` handlers live in Python (`anki.speedrun.*`) over a
held-out corpus / templated bank and are NOT in the shared Rust engine, so they
are intentionally **not** re-implemented in Kotlin (that would risk diverging from
the desktop's graded evidence + the leakage rule):

- `speedrun-assemble-test` / `speedrun-record-test` (practice-test bank + grading)
  → return an empty result on the phone; the screen renders but a test can't be
  taken until the assembly/grading move into the engine as an RPC.
- `speedrun-classify` (AI/keyword subtopic suggestion for add-card) → returns no
  suggestions; the manual subtopic dropdown still works, so add-card saves.
- the deck-preset new/day-limit edit is a desktop-only no-op (it edits an Anki
  deck preset on desktop). Unlimited cram (`speedrun-practice*`) shows a "desktop
  only" toast rather than faking the memory/performance separation. (The
  `speedrun-set-theme` toggle is **no longer** a no-op; see "Light/dark theme".)

Nothing is fabricated on the client: the phone renders exactly what the shared
engine returns, behind the same give-up rule as the desktop.
