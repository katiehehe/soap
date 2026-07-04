#!/usr/bin/env bash
#
# Start Anki's built-in sync server (the SAME Rust sync protocol the phone and
# desktop use) for local phone<->desktop sync — no AnkiWeb account needed.
#
# It binds all interfaces so the Android emulator can reach it. From the host use
#   http://127.0.0.1:$SYNC_PORT/
# From the AnkiDroid emulator use the host-loopback alias
#   http://10.0.2.2:$SYNC_PORT/
#
# Login is a local account defined here (default user/pass), NOT AnkiWeb.
#
# Usage:
#   tools/speedrun/sync_server.sh          # run in foreground (Ctrl-C to stop)
#   make sync-server                       # same, via Makefile
#
# Env overrides: SYNC_HOST, SYNC_PORT, SYNC_BASE, SYNC_USER1 (user:pass).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY="$REPO/out/pyenv/bin/python"
[ -x "$PY" ] || { echo "python not built yet at $PY — run ./run once first" >&2; exit 1; }

export SYNC_HOST="${SYNC_HOST:-0.0.0.0}"
export SYNC_PORT="${SYNC_PORT:-27701}"
export SYNC_BASE="${SYNC_BASE:-$REPO/out/sync-server}"
export SYNC_USER1="${SYNC_USER1:-user:pass}"
export RUST_LOG="${RUST_LOG:-info}"
export PYTHONPATH="$REPO/pylib:$REPO/out/pylib"

mkdir -p "$SYNC_BASE"

echo "Anki sync server starting"
echo "  host bind : $SYNC_HOST:$SYNC_PORT"
echo "  from host : http://127.0.0.1:$SYNC_PORT/"
echo "  from phone: http://10.0.2.2:$SYNC_PORT/   (Android emulator host alias)"
echo "  login     : user='${SYNC_USER1%%:*}'  pass='${SYNC_USER1#*:}'   (local, not AnkiWeb)"
echo "  data dir  : $SYNC_BASE"
cd "$REPO"
exec "$PY" -m anki.syncserver
