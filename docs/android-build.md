# Android build status + reproducible recipe

The "shared engine on the phone" track. Status: **the AnkiDroid APK now builds
against our fork's engine and embeds it**: the desktop and phone run the same
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
  contains `lib/arm64-v8a/librsdroid.so` (48 MB stripped), i.e. our shared Rust
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

## Rebuild gotcha: a stale nested-submodule gitdir blocks the commit move

`make phone-rebuild` moves the backend's `anki` submodule to soap's HEAD
(`git checkout <sha>`) before overlaying the working tree. Two **nested**
submodules of `anki`, `qt/installer/mac-template` (`briefcase-mac-template`) and
`qt/installer/windows-template` (`briefcase-windows-template`), used only for the
*desktop* installer and irrelevant to the Android engine, can carry a stale
`.git` gitdir pointer:

    gitdir: ../../../.git/modules/briefcase-mac-template        # WRONG

`anki`'s own `.git` is a *file* (`gitdir: ../.git/modules/anki`), so the real
nested git dirs live one level deeper. With the wrong pointer, the checkout
aborts with `fatal: not a git repository: .../.git/modules/briefcase-mac-template`
and phone-rebuild silently **falls back to the OLD submodule commit** (warning:
"couldn't move submodule …"), so the phone would be built minus every *committed*
change since that old commit. Fix = repoint each nested `.git` (one extra `../`
plus the `anki/modules/` segment):

    qt/installer/mac-template/.git:
      gitdir: ../../../../.git/modules/anki/modules/briefcase-mac-template
    qt/installer/windows-template/.git:
      gitdir: ../../../../.git/modules/anki/modules/briefcase-windows-template

Also: `phone-rebuild.sh` runs `git checkout` *before* its `git reset --hard` +
`git clean`, so a submodule left dirty by a prior overlay **and** needing a commit
move fails the checkout ("local changes would be overwritten"). Reset+clean the
submodule first, then check out soap HEAD:

```bash
cd ~/dev/projects/speedrun/Anki-Android-Backend/anki
git reset --hard HEAD && git clean -fdq        # clean prior overlay (keeps out/, target/)
git checkout <soap-HEAD-sha>                    # after the nested-.git fix above
```

Once the submodule sits at soap HEAD, phone-rebuild sees `SUB_HEAD == SOAP_HEAD`
and skips the checkout on later runs (so this only bites when soap HEAD advances).

## Reproducible recipe (needs ~8-10 GB free disk)

```bash
# 1. Point the backend's anki submodule at our fork (has the speedrun engine).
cd ~/dev/projects/speedrun/Anki-Android-Backend/anki
git remote add fork /Users/katiehe/dev/projects/speedrun/soap   # once
git fetch fork
git checkout fork/main

# 2. Build the .aar (cross-compiles our engine for arm64-v8a).
cd ~/dev/projects/speedrun/Anki-Android-Backend
export ANDROID_HOME="$HOME/Library/Android/sdk"
export JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"
export PATH="$JAVA_HOME/bin:$PATH"
./build.sh

# 3. Tell AnkiDroid to consume the local .aar instead of the published backend.
grep -q '^local_backend=true' ~/dev/projects/speedrun/Anki-Android/local.properties \
  || echo 'local_backend=true' >> ~/dev/projects/speedrun/Anki-Android/local.properties

# 4. Add the one enum branch in
#    Anki-Android/libanki/src/main/java/com/ichi2/anki/libanki/Deck.kt
#    (Order.toDisplayString): see snippet above.

# 5. Build the APK.
cd ~/dev/projects/speedrun/Anki-Android
./gradlew assemblePlayDebug
# -> AnkiDroid/build/outputs/apk/play/debug/AnkiDroid-play-arm64-v8a-debug.apk
```

Only `arm64-v8a` carries our engine (that's the ABI we cross-compiled, and it's
the right one for the Apple-silicon emulator and modern phones). The other ABI
splits build but won't have `librsdroid.so`.

## Run it on the emulator

An AVD named `Speedrun_P` already exists (arm64).

```bash
export ANDROID_HOME="$HOME/Library/Android/sdk"
"$ANDROID_HOME/emulator/emulator" -avd Speedrun_P &     # or -no-window for headless
"$ANDROID_HOME/platform-tools/adb" wait-for-device
# wait until: adb shell getprop sys.boot_completed  -> 1
"$ANDROID_HOME/platform-tools/adb" install -r \
  ~/dev/projects/speedrun/Anki-Android/AnkiDroid/build/outputs/apk/play/debug/AnkiDroid-play-arm64-v8a-debug.apk
```

Then load the Exam P deck (export a `.colpkg` from desktop or sync) and run a
review session: it exercises the same scheduler/engine as desktop.

## Notes

- The changes in step 1, 3, 4 live in the two external clones, not in this repo.
  Keep them if you rebuild; `git checkout fork/main` in the submodule is what
  swaps upstream Anki for our engine.
- The desktop + Android builds are disk-hungry. Free regenerable caches
  (`~/Library/Caches`, `~/.cache`, cargo tarball cache) before rebuilding if low.

## Release build (signed hand-in APK)

The debug APK above is what we test/record with. The hand-in deliverable is a
**properly packaged, R8-minified, release-signed** APK of the same build (same
engine, same working tree, including the uncommitted home-shell Sync-button fix
in `SpeedrunPageFragment.kt`).

**Keystore** (self-signed, lives in `$HOME`, never committed):

```bash
keytool -genkeypair -v -keystore "$HOME/exam-p-release.jks" \
  -storepass examp-speedrun -keypass examp-speedrun -alias exam-p \
  -keyalg RSA -keysize 2048 -validity 10000 \
  -dname "CN=Exam P Speedrun, OU=Dev, O=Katie He, C=US"
```

- Path: `~/exam-p-release.jks` · alias `exam-p` · store/key pass `examp-speedrun`.
- Reuse this same keystore to sign future updates (a new key = users must
  uninstall/reinstall).

**Build**: AnkiDroid's `signingConfigs.release` already reads the keystore from
env vars (falls back to a throwaway test key only if `KEYSTOREPATH` is unset), so
Gradle signs + zipaligns the release APK directly; no manual `apksigner` needed:

```bash
export ANDROID_HOME="$HOME/Library/Android/sdk"
export JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"
export PATH="$JAVA_HOME/bin:$PATH"
export KEYSTOREPATH="$HOME/exam-p-release.jks"
export KEYSTOREPWD="examp-speedrun"   # code also accepts KSTOREPWD
export KEYALIAS="exam-p"
export KEYPWD="examp-speedrun"
cd ~/dev/projects/speedrun/Anki-Android
./gradlew :AnkiDroid:assemblePlayRelease
# -> AnkiDroid/build/outputs/apk/play/release/AnkiDroid-play-arm64-v8a-release.apk
```

**One fix required for the release variant** (release runs `lintVitalPlayRelease`,
which debug does not): AnkiDroid's custom `MenuTitleMaxLengthAttr` lint fails the
build because our two nav-drawer menu-title strings lacked the repo-standard
`maxLength` attribute. Fixed in `AnkiDroid/.../res/values/speedrun.xml` (a
lint/translator hint only, no runtime effect), matching `sentence-case.xml`:

```xml
<string name="speedrun_readiness_title" maxLength="28">Exam readiness</string>
<string name="speedrun_home_title" maxLength="28">Exam P</string>
```

R8/minify (`minifyPlayReleaseWithR8`) runs **on** and succeeds on our engine, so
no ProGuard changes needed. The WebView bridge survives R8 via the stock keep
rules (`-keep class com.ichi2.anki.**.*Fragment { *; }` + the AGP default
`@JavascriptInterface` keep + the protobuf keep). So `minifyEnabled=false` was
**not** needed; if it ever is, `MINIFY_ENABLED=false ./gradlew ...` toggles it.

**Verified deliverable** (arm64-v8a is the only split that carries our engine):

```bash
BT="$ANDROID_HOME/build-tools/35.0.0"
APK=AnkiDroid/build/outputs/apk/play/release/AnkiDroid-play-arm64-v8a-release.apk
"$BT/apksigner" verify --print-certs "$APK"   # CN=Exam P Speedrun (not debug key); Verifies (v2)
unzip -l "$APK" | grep librsdroid             # lib/arm64-v8a/librsdroid.so (~48 MB) embedded
"$BT/aapt" dump badging "$APK" | grep versionName   # com.ichi2.anki 2.25.0alpha1
```

- Signed cert: `CN=Exam P Speedrun, OU=Dev, O=Katie He, C=US`
  (SHA-256 `582fe62a2aa61d3adfcbc660853fdc114a37b1719ddeee9770217e27691485e6`).
- APK **verifies** (APK Signature Scheme v2; v1 is correctly skipped since
  `minSdk=24`), zipaligned (incl. 16 KB `.so` page alignment).
- `lib/arm64-v8a/librsdroid.so` (our shared Rust engine) embedded.
- package `com.ichi2.anki`, versionName `2.25.0alpha1`, minSdk 24 / targetSdk 35.
- **Do not** `adb install` this over the debug app on the recording emulator:
  different signature (and the release app id is `com.ichi2.anki`, not
  `...debug`); installing would require uninstalling the debug app and wipe the
  synced deck. Build/sign/verify only.
