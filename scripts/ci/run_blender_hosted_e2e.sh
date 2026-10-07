#!/usr/bin/env bash
set -euo pipefail

blender=$1
site=$2
wheel=$3
evidence=$4
mkdir -p "$evidence"
openbox >"$evidence/window-manager.log" 2>&1 &
wm_pid=$!
trap 'kill "$wm_pid" 2>/dev/null || true; wait "$wm_pid" 2>/dev/null || true' EXIT
sleep 1

set +e
"$blender" --factory-startup --python-exit-code 1 \
  --python scripts/ci/blender_hosted_e2e.py -- \
  --site "$site" --wheel "$wheel" --evidence "$evidence" \
  >"$evidence/blender.log" 2>&1
blender_exit=$?
set -e
cat "$evidence/blender.log"
scrot --overwrite "$evidence/after-exit.png" || true
vx python scripts/ci/blender_hosted_e2e.py --verify \
  --evidence "$evidence" --blender-exit "$blender_exit"
