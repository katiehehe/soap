#!/usr/bin/env bash
#
# Rebuild the phone APK from your CURRENT working tree, then install + open it.
#
# The phone bundles the UI + Rust engine inside the APK, so there is no hot
# reload — this is the (slow) command that gets a code change onto the phone.
# For fast iteration prefer the desktop `./run`; use this to verify on-device.
#
# Why it is more than one build: the engine .aar is compiled from a SEPARATE
# `anki` git submodule inside Anki-Android-Backend, so this script first overlays
# your working-tree changes (including UNCOMMITTED ones) into that submodule, so
# what you see on the phone is exactly what you have here — no commit required.
#
#   1. Sync this repo's working tree into the backend's `anki` submodule.
#   2. Build the engine + UI .aar          (Anki-Android-Backend/build.sh)
#   3. Assemble the debug APK              (Anki-Android/gradlew assemblePlayDebug)
#   4. Boot emulator + install + open      (tools/speedrun/phone.sh --install)
#
# Env overrides: ANDROID_DIR, BACKEND_DIR, ANDROID_HOME, JAVA_HOME.
# Flags: --dry-run  (only show which files would sync; skip the build)
set -euo pipefail

SOAP="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PARENT="$(dirname "$SOAP")"
ANDROID="${ANDROID_DIR:-$PARENT/Anki-Android}"
BACKEND="${BACKEND_DIR:-$PARENT/Anki-Android-Backend}"
SUB="$BACKEND/anki"

export ANDROID_HOME="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
export JAVA_HOME="${JAVA_HOME:-/Applications/Android Studio.app/Contents/jbr/Contents/Home}"
export PATH="$JAVA_HOME/bin:$PATH"

DRY=0
for a in "$@"; do
    case "$a" in
        --dry-run) DRY=1 ;;
        *) echo "unknown option: $a" >&2; exit 2 ;;
    esac
done

for d in "$ANDROID" "$BACKEND" "$SUB"; do
    [ -d "$d" ] || { echo "not found: $d (is the Android checkout a sibling of this repo?)" >&2; exit 1; }
done
[ -x "$JAVA_HOME/bin/java" ] || { echo "JAVA_HOME looks wrong: $JAVA_HOME" >&2; exit 1; }

echo "==> [1/4] Sync working tree -> engine submodule ($SUB)"
# Files to overlay: tracked-and-modified (minus deletes) + new untracked files
# that git isn't ignoring. This naturally excludes out/, target/, node_modules,
# .env, etc. via .gitignore. (Read-only git queries — safe for --dry-run.)
LIST="$(mktemp)"
{ git -C "$SOAP" diff --name-only --diff-filter=d HEAD
  git -C "$SOAP" ls-files --others --exclude-standard; } | sort -u > "$LIST"
N="$(grep -c . "$LIST" || true)"
echo "    $N changed/new file(s) to overlay"

if [ "$DRY" = 1 ]; then
    echo "--- files that would sync (dry run; nothing is modified) ---"
    cat "$LIST"
    rm -f "$LIST"
    echo "==> dry run complete (no build performed)"
    exit 0
fi

# --- mutations start here (skipped entirely on --dry-run) ---
SOAP_HEAD="$(git -C "$SOAP" rev-parse HEAD)"
SUB_HEAD="$(git -C "$SUB" rev-parse HEAD 2>/dev/null || echo none)"
if [ "$SUB_HEAD" != "$SOAP_HEAD" ]; then
    echo "    submodule is at ${SUB_HEAD:0:9}, moving to soap HEAD ${SOAP_HEAD:0:9}"
    git -C "$SUB" fetch --no-tags -q "$SOAP" 2>/dev/null || true
    git -C "$SUB" checkout -q "$SOAP_HEAD" 2>/dev/null \
        || echo "    (warn: couldn't move submodule to $SOAP_HEAD; building on $(git -C "$SUB" rev-parse --short HEAD))"
fi
# Reset to committed state so a previous overlay never leaves stale files.
# `clean` respects .gitignore, so the submodule's build caches (out/, target/,
# node_modules — all gitignored) are preserved for a fast incremental build.
git -C "$SUB" reset -q --hard HEAD 2>/dev/null || echo "    (warn: submodule reset skipped)"
git -C "$SUB" clean -fdq 2>/dev/null || echo "    (warn: submodule clean skipped)"

if [ "$N" -gt 0 ]; then
    rsync -a --files-from="$LIST" "$SOAP"/ "$SUB"/
fi
rm -f "$LIST"

echo "==> [2/4] Build engine + UI .aar  (slow: cross-compiles the Rust engine)"
( cd "$BACKEND" && ./build.sh )

echo "==> [3/4] Assemble debug APK"
( cd "$ANDROID" && ./gradlew assemblePlayDebug )

echo "==> [4/4] Install on the emulator + open"
"$SOAP/tools/speedrun/phone.sh" --install

echo
echo "Done — your working-tree changes are now on the phone. (☰ -> Exam readiness)"
