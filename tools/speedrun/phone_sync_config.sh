#!/usr/bin/env bash
#
# (Re)configure AnkiDroid on the emulator to sync with the LOCAL server, with no
# UI login: writes syncBaseUrl + switch + username + hkey into its
# SharedPreferences (debug build only, via `run-as`). Idempotent — safe to re-run
# if a hard kill lost the prefs.
#
# Prereqs: `make sync-server` running, and the emulator booted (`make phone`).
# Then:    make sync-phone-config
# Finally, in AnkiDroid tap Sync (first time: keep the server copy -> Replace).
#
# Env overrides: PHONE_SYNC_URL, SYNC_ENDPOINT, SYNC_USER, SYNC_PASS, ANDROID_HOME.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ANDROID_HOME="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
ADB="$ANDROID_HOME/platform-tools/adb"
PY="$REPO/out/pyenv/bin/python"
PKG="com.ichi2.anki.debug"
PHONE_URL="${PHONE_SYNC_URL:-http://10.0.2.2:27701/}"   # emulator -> host alias
USER_NAME="${SYNC_USER:-user}"
PREFS="/data/data/$PKG/shared_prefs/${PKG}_preferences.xml"

[ -x "$PY" ] || { echo "python not built ($PY) — run ./run once first" >&2; exit 1; }

# Mint an hkey against the local server (login only, no seeding).
HKEY="$(PYTHONPATH="$REPO/pylib:$REPO/out/pylib" "$PY" "$REPO/tools/speedrun/sync_hkey.py")"
[ -n "$HKEY" ] || { echo "could not get an hkey — is 'make sync-server' running?" >&2; exit 1; }
echo "hkey ${HKEY:0:8}...   server $PHONE_URL   user $USER_NAME"

"$ADB" wait-for-device
"$ADB" shell am force-stop "$PKG" || true
sleep 1

tmp_in="$(mktemp)"; tmp_out="$(mktemp)"
"$ADB" shell run-as "$PKG" cat "$PREFS" 2>/dev/null > "$tmp_in" || true

PHONE_URL="$PHONE_URL" USER_NAME="$USER_NAME" HKEY="$HKEY" \
    "$PY" - "$tmp_in" "$tmp_out" <<'PY'
import os, sys
src, dst = sys.argv[1], sys.argv[2]
url, user, hkey = os.environ["PHONE_URL"], os.environ["USER_NAME"], os.environ["HKEY"]
try:
    xml = open(src).read()
except OSError:
    xml = ""
if "</map>" not in xml:
    xml = "<?xml version='1.0' encoding='utf-8' standalone='yes' ?>\n<map>\n</map>\n"
managed = ('name="syncBaseUrl"', 'name="syncBaseUrl_switch"', 'name="username"', 'name="hkey"')
lines = [ln for ln in xml.splitlines() if not any(m in ln for m in managed)]
entries = [
    '    <string name="syncBaseUrl">%s</string>' % url,
    '    <boolean name="syncBaseUrl_switch" value="true" />',
    '    <string name="username">%s</string>' % user,
    '    <string name="hkey">%s</string>' % hkey,
]
out = []
for ln in lines:
    if ln.strip() == "</map>":
        out.extend(entries)
    out.append(ln)
open(dst, "w").write("\n".join(out) + "\n")
print("prefs updated")
PY

"$ADB" push "$tmp_out" /data/local/tmp/ad_prefs.xml >/dev/null
"$ADB" shell run-as "$PKG" cp /data/local/tmp/ad_prefs.xml "$PREFS"
"$ADB" shell rm /data/local/tmp/ad_prefs.xml 2>/dev/null || true
rm -f "$tmp_in" "$tmp_out"

echo "done. Open AnkiDroid and tap Sync (top-right)."
