# Android build status + reproducible recipe

The "shared engine on the phone" track. Status: **the AnkiDroid APK now builds
against our fork's engine and embeds it** — the desktop and phone run the same
Rust backend (with the speedrun changes), which is what the PRD requires.

## What is done (verified)

- `Anki-Android` and `Anki-Android-Backend` cloned as siblings under `~/dev/`.
- Toolchain: Android SDK cmdline-tools, **NDK `29.0.14206865`** (pinned in
  `Anki-Android-Backend/gradle/libs.versions.toml`), `cargo-ndk 4.1.2`, Rust
  target `aarch64-linux-android`, Android Studio JBR (Java 21) as `JAVA_HOME`.
- **The backend `anki` submodule is repointed at THIS fork**, so the engine that
  gets cross-compiled is ours (speedrun proto/service included).
- **The engine cross-compiles for Android and the `.aar` is built from our fork:**
  - `rsdroid/build/generated/jniLibs/arm64-v8a/librsdroid.so` (our engine)
  - `rsdroid/build/outputs/aar/rsdroid-release.aar`
  - `rsdroid-testing/build/libs/rsdroid-testing.jar`
- **AnkiDroid builds a debug APK that embeds our engine:**
  `AnkiDroid/build/outputs/apk/play/debug/AnkiDroid-play-arm64-v8a-debug.apk`
  contains `lib/arm64-v8a/librsdroid.so` (48 MB stripped) — i.e. our shared Rust
  backend, on the phone.

## The one real incompatibility (and its fix)

Our fork's Anki base is newer (≈26.05) than the Anki version this AnkiDroid
checkout targets (`0.1.64-anki25.09.2`). The newer engine adds one filtered-deck
sort order, `Order.RELATIVE_OVERDUENESS`, which AnkiDroid's `when` did not handle:

    libanki/src/main/java/com/ichi2/anki/libanki/Deck.kt:127
    'when' expression must be exhaustive. Add the 'RELATIVE_OVERDUENESS' branch...

That was the **only** Kotlin error across the whole build (Kotlin reports all
errors in a module at once), which confirms the rest of our engine's API matches
what this AnkiDroid expects. Fix = add the missing branch, using the translation
that our engine already ships (`decks-relative-overdueness`):

```kotlin
Order.RELATIVE_OVERDUENESS -> translations.decksRelativeOverdueness()
```

## Reproducible recipe (needs ~8-10 GB free disk)

```bash
# 1. Point the backend's anki submodule at our fork (has the speedrun engine).
cd ~/dev/Anki-Android-Backend/anki
git remote add fork /Users/katiehe/dev/soap   # once
git fetch fork
git checkout fork/main

# 2. Build the .aar (cross-compiles our engine for arm64-v8a).
cd ~/dev/Anki-Android-Backend
export ANDROID_HOME="$HOME/Library/Android/sdk"
export JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"
export PATH="$JAVA_HOME/bin:$PATH"
./build.sh

# 3. Tell AnkiDroid to consume the local .aar instead of the published backend.
grep -q '^local_backend=true' ~/dev/Anki-Android/local.properties \
  || echo 'local_backend=true' >> ~/dev/Anki-Android/local.properties

# 4. Add the one enum branch in
#    Anki-Android/libanki/src/main/java/com/ichi2/anki/libanki/Deck.kt
#    (Order.toDisplayString): see snippet above.

# 5. Build the APK.
cd ~/dev/Anki-Android
./gradlew assemblePlayDebug
# -> AnkiDroid/build/outputs/apk/play/debug/AnkiDroid-play-arm64-v8a-debug.apk
```

Only `arm64-v8a` carries our engine (that's the ABI we cross-compiled, and it's
the right one for the Apple-silicon emulator and modern phones). The other ABI
splits build but won't have `librsdroid.so`.

## Run it on the emulator

An AVD named `Medium_Phone` already exists (arm64).

```bash
export ANDROID_HOME="$HOME/Library/Android/sdk"
"$ANDROID_HOME/emulator/emulator" -avd Medium_Phone &     # or -no-window for headless
"$ANDROID_HOME/platform-tools/adb" wait-for-device
# wait until: adb shell getprop sys.boot_completed  -> 1
"$ANDROID_HOME/platform-tools/adb" install -r \
  ~/dev/Anki-Android/AnkiDroid/build/outputs/apk/play/debug/AnkiDroid-play-arm64-v8a-debug.apk
```

Then load the Exam P deck (export a `.colpkg` from desktop or sync) and run a
review session — it exercises the same scheduler/engine as desktop.

## Notes

- The changes in step 1, 3, 4 live in the two external clones, not in this repo.
  Keep them if you rebuild; `git checkout fork/main` in the submodule is what
  swaps upstream Anki for our engine.
- The desktop + Android builds are disk-hungry. Free regenerable caches
  (`~/Library/Caches`, `~/.cache`, cargo tarball cache) before rebuilding if low.
