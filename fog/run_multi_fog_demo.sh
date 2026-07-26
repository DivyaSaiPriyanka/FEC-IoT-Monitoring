#!/usr/bin/env bash
# ----------------------------------------------------------------------
# run_multi_fog_demo.sh
#
# Launches two independent virtual fog nodes against the same backend,
# useful for the CA demo to show the platform handling multiple
# fog nodes / edge locations concurrently (strengthens the "sensor and
# fog application" mark - the brief allows "fog node(s)", plural).
#
# Usage:
#   ./run_multi_fog_demo.sh http://<backend-host>:8000/api/ingest
# ----------------------------------------------------------------------
set -euo pipefail

BACKEND_URL="${1:-http://localhost:8000/api/ingest}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Starting fog-node-A and fog-node-B against ${BACKEND_URL}"

python "${SCRIPT_DIR}/fog_node.py" --backend-url "${BACKEND_URL}" --node-id fog-node-A --dispatch-interval 5 &
PID_A=$!

python "${SCRIPT_DIR}/fog_node.py" --backend-url "${BACKEND_URL}" --node-id fog-node-B --dispatch-interval 7 &
PID_B=$!

trap 'echo "Stopping fog nodes..."; kill "${PID_A}" "${PID_B}" 2>/dev/null' EXIT INT TERM

echo "fog-node-A pid=${PID_A}, fog-node-B pid=${PID_B}. Press Ctrl+C to stop."
wait
