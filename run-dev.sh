#!/usr/bin/env bash
# Start FalloutCast's API (:8010) + web dev server (:5173) and keep them up.
#
# Run this in your OWN Terminal and leave the window open:
#     bash run-dev.sh
#
# Both servers auto-restart if they exit. Press Ctrl-C to stop both.
# Logs stream here; the app is at http://localhost:5173
set -u
cd "$(dirname "$0")"
ROOT="$PWD"

run_api() {
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
  export PYTHONPATH="$ROOT/src:${PYTHONPATH:-}"
  while true; do
    echo "[$(date +%H:%M:%S)] [api] starting on http://localhost:8010"
    uvicorn falloutcast.api.main:app --port 8010
    echo "[$(date +%H:%M:%S)] [api] stopped — restarting in 2s"; sleep 2
  done
}

run_web() {
  while true; do
    echo "[$(date +%H:%M:%S)] [web] starting on http://localhost:5173"
    npm --prefix "$ROOT/web" run dev
    echo "[$(date +%H:%M:%S)] [web] stopped — restarting in 2s"; sleep 2
  done
}

# Kill both background loops (and their children) when this script is stopped.
trap 'kill 0' EXIT INT TERM

run_api &
run_web &
wait
