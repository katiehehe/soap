# The three scores on the phone (Friday, mobile)

The Friday mobile item asks that the phone "shows the three scores with ranges and
follows the give-up rule." Here is the honest status and how to verify it.

## The scoring lives in the shared engine, not the UI

All three signals are computed by the **Rust engine** that ships to both desktop
and phone (`rslib/src/speedrun/`), behind one give-up rule:

- `compute_readiness` returns `oneof { NoScore, ReadinessScore }` — a bare number
  literally cannot be emitted below threshold, on **either** platform.
- `get_mastery_state` (the measured mastery signal) and the FSRS memory signal are
  the same code on both.

The AnkiDroid build is compiled from **our** engine, so these RPCs are present in
the on-device binary. Proof (from `docs/demo-script.md`):

```bash
APK=~/dev/Anki-Android/AnkiDroid/build/outputs/apk/play/debug/AnkiDroid-play-arm64-v8a-debug.apk
unzip -p "$APK" lib/arm64-v8a/librsdroid.so | strings | grep -iE "ComputeReadiness|Mastery|speedrun"
# -> anki/rslib/src/speedrun/service.rs, ComputeReadinessRequest, MasteryRequest, ...
```

Because desktop and phone share one collection via sync, once the phone syncs the
demo-persona collection (`make seed-persona`, then sync), `compute_readiness` on
the phone returns the **same** honesty-bundled band the desktop shows — same
engine, same inputs, same number.

## What is built — the SAME UI build on the phone (WebView parity)

The phone renders the **exact same Svelte UI build** as the desktop, not a
re-implementation. AnkiDroid renders Anki's Svelte "pages" in a WebView
(`com.ichi2.anki.pages.PageFragment`), and our whole sveltekit app — including
every custom route — is bundled into the engine `.aar` and packaged in the APK
(`assets/backend/sveltekit`; verified: all 19 route chunks present, including the
new `formula-sheet`/`metrics`/`practice-test`/`add-card`).

**The app now launches straight into the Svelte `home` shell** — the phone analog
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
- **`window.bridgeCommand("speedrun-*", cb)`** — handled by a new
  `SpeedrunPageFragment` base that mirrors the desktop `qt/aqt/speedrun.py`
  handlers in Kotlin. AnkiDroid's stock `PageFragment` bridge is void + exact-match
  only and can't return a value to a callback, so `SpeedrunPageFragment` injects a
  callback-capable `window.bridgeCommand` (synchronous `@JavascriptInterface`
  returning JSON) that dispatches config writes, deck opening, settings, and the
  formula-sheet/add-card reads on the SHARED collection (which syncs to desktop).

### Files (in the AnkiDroid clone, `Anki-Android/`)

Not part of this repo's git; they live in the sibling AnkiDroid checkout that
consumes our engine `.aar` (see `docs/android-build.md`):

- **`pages/SpeedrunPageFragment.kt` (new)** — base class: the callback-capable
  `speedrun-*` bridge (settings, set-scheduler/guided/ai/exam-date/unlock,
  nav:browse/decks/sync/stats/study, study/study-unit/study-all/study-deck,
  formula-cards, add-card). Practice-test assemble/grade + AI classify return an
  empty result (see gaps below).
- **`pages/HomePage.kt` (new)** — `SpeedrunPageFragment(pagePath="home")`,
  full-bleed (`res/layout/fragment_speedrun_home.xml`, no Anki toolbar). The
  landing screen.
- **`pages/StudyMapPage.kt`, `PracticeTestPage.kt`, `FormulaSheetPage.kt`,
  `MetricsPage.kt` (new)** — standalone entry points / deep links for each route
  (also reached as tabs inside `home`).
- `pages/ReadinessDashboardPage.kt` — unchanged (still a `PageFragment`).
- **`DeckPicker.kt`** — on a normal launcher start (`ACTION_MAIN`, fresh create) it
  now `startActivity(HomePage.getIntent(this))`; guarded so review/import/sync
  flows are untouched.
- **`pages/PageWebViewClient.kt`** — `isSvelteKitPage` allowlist extended with
  `practice-test`, `formula-sheet`, `metrics`, `add-card` (mirrors the desktop
  `is_sveltekit_page`).
- **`NavigationDrawerActivity.kt` + `res/menu/navigation_drawer.xml`** — added a
  **Home** drawer entry → `HomePage`.
- `pages/PostRequestHandler.kt` — the SpeedrunService RPCs were already registered.
- **Deleted:** `ReadinessScoresActivity.kt` + `res/layout/activity_readiness_scores.xml`
  + its `AndroidManifest.xml` entry. That native Kotlin screen re-drew the scores
  outside the WebView; readiness now stays engine-sourced via the Svelte route
  (honesty rule).
- `gradle/libs.versions.toml` — `ankiBackend` bumped `0.1.64-anki25.09.2` →
  `0.1.65-anki26.05b1` (matches the local backend `VERSION_NAME`, so a non-local
  build can't silently pull stock upstream Anki).

### How it was verified (emulator `Medium_Phone`, arm64)

- Rebuilt the local AAR (`cargo run -p build_rust`): `librsdroid.so` carries our
  engine (`ComputeReadinessRequest`, `speedrunMasteryScheduler`, …) and the fresh
  sveltekit bundle includes all routes.
- `./gradlew :AnkiDroid:assemblePlayDebug` **succeeds**; the new Kotlin compiles
  clean; installed the arm64 APK.
- On launch the app opens the **Svelte `home` shell full-bleed** (logcat:
  `PageFragment: Loading http://127.0.0.1:PORT/home`,
  `SingleFragmentActivity::HomePage::onResume`, `ResumedActivity=…SingleFragmentActivity`,
  no `FATAL`). The Map/Readiness/How-it-works/Formulas tabs all render and their
  engine calls fire (`AnkiServer: POST /_anki/{getMasteryState,computeReadiness,
  getStudyPlan,getStudyPace}`). Readiness shows the three separate signals with the
  honest abstain state; "How it works" shows the give-up rule "enforced in Rust".

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
- `speedrun-set-theme` (desktop Qt theme) and the deck-preset new/day edit are
  desktop-only no-ops; theme follows Android day/night. Unlimited cram
  (`speedrun-practice*`) shows a "desktop only" toast rather than faking the
  memory/performance separation.

Nothing is fabricated on the client: the phone renders exactly what the shared
engine returns, behind the same give-up rule as the desktop.
