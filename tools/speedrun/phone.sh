#!/usr/bin/env bash
#
# Boot the phone emulator and open AnkiDroid (our SOA Exam P fork).
#
# Usage:
#   tools/speedrun/phone.sh              # boot the emulator (if needed) + open AnkiDroid
#   tools/speedrun/phone.sh --install    # (re)install the freshest built APK first
#
# Or via the Makefile:
#   make phone           # boot + open
#   make phone-install   # boot + reinstall freshest APK + open
#
# Env overrides: AVD, ANDROID_HOME, APK.
set -euo pipefail

AVD="${AVD:-Medium_Phone}"
ANDROID_HOME="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
EMU="$ANDROID_HOME/emulator/emulator"
ADB="$ANDROID_HOME/platform-tools/adb"
PKG="com.ichi2.anki.debug"
# The AnkiDroid checkout is a sibling of this repo (…/speedrun/Anki-Android).
SOAP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APK="${APK:-$(dirname "$SOAP_DIR")/Anki-Android/AnkiDroid/build/outputs/apk/play/debug/AnkiDroid-play-arm64-v8a-debug.apk}"

INSTALL=0
for a in "$@"; do
    case "$a" in
        --install) INSTALL=1 ;;
        *) echo "unknown option: $a" >&2; exit 2 ;;
    esac
done

[ -x "$EMU" ] || { echo "emulator not found at $EMU (is the Android SDK installed?)" >&2; exit 1; }
"$EMU" -list-avds 2>/dev/null | grep -qx "$AVD" || {
    echo "AVD '$AVD' not found. Available:" >&2
    "$EMU" -list-avds 2>/dev/null >&2
    exit 1
}

# 1. Boot the emulator if it isn't already running.
if pgrep -f "qemu-system.*$AVD" >/dev/null; then
    echo "emulator '$AVD' already running"
else
    echo "starting emulator '$AVD' ..."
    # -no-snapshot-load: always cold-boot. A hard kill (e.g. OOM) can leave a
    # corrupt saved snapshot that hangs the next boot at "Vulkan emulation
    # initialized"; ignoring the snapshot avoids that at the cost of a slower
    # (~1-2 min) but reliable boot.
    nohup "$EMU" -avd "$AVD" -no-snapshot-load -no-boot-anim \
        >"/tmp/emulator-$AVD.log" 2>&1 &
    disown || true
fi

# 2. Wait for the device to finish booting.
echo "waiting for boot (first cold boot can take a minute) ..."
"$ADB" wait-for-device
until [ "$("$ADB" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; do
    sleep 2
done
echo "booted."

# 3. Optionally (re)install the freshest built APK.
if [ "$INSTALL" = 1 ]; then
    if [ -f "$APK" ]; then
        echo "installing $APK ..."
        "$ADB" install -r "$APK"
    else
        echo "APK not found at $APK" >&2
        echo "build it in the Anki-Android checkout: ./gradlew assemblePlayDebug (see docs/android-build.md)" >&2
    fi
fi

# 4. Open AnkiDroid (routes through IntentHandler -> DeckPicker).
echo "opening AnkiDroid ..."
"$ADB" shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1

echo
echo "Done. In the app: tap the  hamburger (top-left)  ->  Exam readiness  to see the three scores."
