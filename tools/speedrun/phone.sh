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
# Env overrides: AVD, ANDROID_HOME, APK, EMU_MEM, EMU_CORES, EMU_GPU.
set -euo pipefail

# Speedrun_P: lean AVD (AOSP Android 34, no Play Store) sized for an 8 GB Mac,
# using a 2 GB guest + Metal host GPU. The old heavyweight "Medium_Phone" (Android 37 +
# Play Store + 16 KB) forces a 4 GB guest and software rendering on this host, so
# it is no longer the default; use `AVD=Medium_Phone make phone` to fall back.
AVD="${AVD:-Speedrun_P}"
ANDROID_HOME="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
EMU="$ANDROID_HOME/emulator/emulator"
ADB="$ANDROID_HOME/platform-tools/adb"
PKG="com.ichi2.anki.debug"
# The AnkiDroid checkout is a sibling of this repo (…/speedrun/Anki-Android).
SOAP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APK="${APK:-$(dirname "$SOAP_DIR")/Anki-Android/AnkiDroid/build/outputs/apk/play/debug/AnkiDroid-play-arm64-v8a-debug.apk}"

# --- Emulator resource tuning ---------------------------------------------
# This dev box is an 8 GB M1 Air. Left to its defaults the AVD grabbed ~4 GB of
# guest RAM (half the machine → the host went 6 GB into swap and everything,
# including the emulator, crawled) and rendered on the CPU via the software
# "lavapipe" GPU (a pegged core, stuttery UI). The knobs below keep the guest
# lean and force the Metal-accelerated host GPU. Override any via the env, e.g.
#   EMU_MEM=3072 EMU_GPU=swiftshader_indirect make phone
EMU_MEM="${EMU_MEM:-2048}"     # guest RAM in MB
EMU_CORES="${EMU_CORES:-4}"    # guest CPU cores
EMU_GPU="${EMU_GPU:-host}"     # host = Metal accel; swiftshader_indirect = software fallback

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

# 1+2. Boot the emulator (if needed) with the resource tuning above, then wait
# for it to finish booting. If a host-GPU boot doesn't complete in time (some
# preview system images want Vulkan features the host can't provide), fall back
# once to the software renderer so `make phone` still comes up.
boot_and_wait() {
    local gpu="$1"
    echo "starting emulator '$AVD' (gpu=$gpu, mem=${EMU_MEM}M, cores=$EMU_CORES) ..."
    # -no-snapshot-load: always cold-boot. A hard kill (e.g. OOM) can leave a
    # corrupt saved snapshot that hangs the next boot at "Vulkan emulation
    # initialized"; ignoring the snapshot avoids that at the cost of a slower
    # (~1-2 min) but reliable boot.
    nohup "$EMU" -avd "$AVD" -no-snapshot-load -no-boot-anim -no-audio \
        -gpu "$gpu" -memory "$EMU_MEM" -cores "$EMU_CORES" \
        >"/tmp/emulator-$AVD.log" 2>&1 &
    disown || true

    # A first cold boot on a fresh userdata can take 3-4 min on a loaded machine
    # (the emulator itself warns "up to two minutes, or more"), so give it a
    # generous 360s before declaring the host-GPU boot a hang and falling back.
    echo "waiting for boot (first cold boot can take a few minutes) ..."
    "$ADB" wait-for-device
    local deadline=$(( $(date +%s) + 360 ))
    until [ "$("$ADB" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; do
        [ "$(date +%s)" -ge "$deadline" ] && return 1
        sleep 3
    done
    return 0
}

if pgrep -f "qemu-system.*$AVD" >/dev/null; then
    echo "emulator '$AVD' already running"
    "$ADB" wait-for-device
elif ! boot_and_wait "$EMU_GPU"; then
    echo "boot did not complete with gpu=$EMU_GPU; retrying with software GPU ..." >&2
    "$ADB" emu kill 2>/dev/null || true
    pkill -f "qemu-system.*$AVD" 2>/dev/null || true
    sleep 3
    boot_and_wait "swiftshader_indirect" || { echo "emulator failed to boot" >&2; exit 1; }
fi
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
