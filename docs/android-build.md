# Android build status + finish-line recipe

This documents the Wednesday Android bring-up: what is done, the one remaining
blocker, and the exact commands to finish. The desktop core is complete; this is
the "shared engine on the phone" track.

## What is done (verified)

- `Anki-Android` and `Anki-Android-Backend` cloned as siblings under `~/dev/`.
- Toolchain installed: Android SDK command-line tools, **NDK `29.0.14206865`**
  (the version pinned in `Anki-Android-Backend/gradle/libs.versions.toml`),
  `cargo-ndk 4.1.2`, Rust target `aarch64-linux-android`. Android Studio JBR used
  as `JAVA_HOME`.
- **The shared Rust engine cross-compiles for Android:**
  `Anki-Android-Backend/rsdroid/build/generated/jniLibs/arm64-v8a/librsdroid.so`.
- **The backend `.aar` + Robolectric `.jar` build cleanly** (`*** Build complete.`,
  `BUILD SUCCESSFUL`):
  - `Anki-Android-Backend/rsdroid/build/outputs/aar/rsdroid-release.aar`
  - `Anki-Android-Backend/rsdroid-testing/build/libs/rsdroid-testing.jar`
- AnkiDroid wired to consume the local backend: `Anki-Android/local.properties`
  has `local_backend=true`, which makes `AnkiDroid/build.gradle` load the two
  files above directly.
- AnkiDroid builds through configuration, dependency resolution, and most Kotlin
  compilation.

## The one blocker: a version skew (not our code)

`./gradlew assemblePlayDebug` fails in `:libanki:compileDebugKotlin`:

    Deck.kt:127 'when' expression must be exhaustive.
    Add the 'RELATIVE_OVERDUENESS' branch or an 'else' branch.

Cause: the two repos are at different Anki versions.

- AnkiDroid clone (`v2.25.0alpha1-119-g65577ec181`) targets backend
  `0.1.64-anki25.09.2` (see `Anki-Android/gradle/libs.versions.toml`).
- But `Anki-Android-Backend`'s `anki` submodule is at **26.05b1**, which added the
  `Order.RELATIVE_OVERDUENESS` enum value that this AnkiDroid does not handle.

So the `.aar` we built contains upstream **26.05b1**, which both mismatches
AnkiDroid and is not our engine. The fix aligns versions AND ships our engine.

## Finish-line recipe (needs ~6-8 GB free disk)

Point the backend's `anki` submodule at THIS fork (25.09.99 - same 25.09 line as
AnkiDroid's expected 25.09.2), then rebuild.

```bash
cd ~/dev/Anki-Android-Backend
# Use a backend commit whose rsdroid bridge targets the 25.09 API (matches
# AnkiDroid's 0.1.64-anki25.09.2), then point its anki submodule at our fork:
cd anki
git remote add fork /Users/katiehe/dev/soap
git fetch fork
git checkout fork/main            # our fork @ 25.09.99 (has the speedrun engine)
cd ..

export ANDROID_HOME="$HOME/Library/Android/sdk"
export JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"
export ANDROID_NDK_HOME="$ANDROID_HOME/ndk/29.0.14206865"
./build.sh                        # rebuilds .aar from our engine

cd ~/dev/Anki-Android
./gradlew assemblePlayDebug       # local_backend=true already set
```

If a residual enum/API mismatch remains, also check out `Anki-Android-Backend`
itself at the tag matching `0.1.64-anki25.09.2` before repointing the submodule,
so `rsdroid` targets the same engine API AnkiDroid expects.

APK output: `Anki-Android/AnkiDroid/build/outputs/apk/play/debug/AnkiDroid-play-debug.apk`.

## Emulator handoff (your step)

An AVD named `Medium_Phone` already exists.

```bash
export ANDROID_HOME="$HOME/Library/Android/sdk"
"$ANDROID_HOME/emulator/emulator" -avd Medium_Phone &
"$ANDROID_HOME/platform-tools/adb" wait-for-device
"$ANDROID_HOME/platform-tools/adb" install -r \
  ~/dev/Anki-Android/AnkiDroid/build/outputs/apk/play/debug/AnkiDroid-play-debug.apk
```

Then load the Exam P deck (export a `.colpkg` from desktop or use sync) and run a
review session on the shared engine.

## Note on disk

The desktop + Android builds already use a lot of space on this machine
(~7 GB free at last check). The rebuild above needs headroom; free space first if
needed. This is why the final rebuild was deferred rather than run automatically.
