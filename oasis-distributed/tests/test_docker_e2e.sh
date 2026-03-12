#!/bin/bash
# Docker Compose E2E Smoke Test
# Requires: Docker Desktop running, poetry.lock + full OASIS deps for coordinator image
# Usage: bash tests/test_docker_e2e.sh
set -euo pipefail
cd "$(dirname "$0")/.."

cleanup() {
  echo "Cleaning up..."
  MIROFISH_CLUSTER_TOKEN=test-e2e docker compose -f docker-compose.distributed.yml down --volumes --remove-orphans 2>/dev/null || true
}
trap cleanup EXIT

# 1. Build images
echo "=== Building images ==="
docker compose -f docker-compose.distributed.yml build

# 2. Start with 1 round, 2 workers
echo "=== Starting 1-round simulation with 2 workers ==="
MIROFISH_CLUSTER_TOKEN=test-e2e \
  TOTAL_ROUNDS=1 \
  EXPECTED_WORKERS=2 \
  docker compose -f docker-compose.distributed.yml up --scale worker=2 --abort-on-container-exit --timeout 120 2>&1 | tee /tmp/e2e-output.log &

COMPOSE_PID=$!

# 3. Wait for completion (max 180s)
if timeout 180 wait $COMPOSE_PID; then
  EXIT_CODE=0
else
  EXIT_CODE=$?
fi

# 4. Check logs for success markers
if [ $EXIT_CODE -eq 0 ] && grep -q "Simulation complete" /tmp/e2e-output.log; then
  echo "=== E2E PASSED ==="
else
  echo "=== E2E FAILED — check /tmp/e2e-output.log ==="
  tail -30 /tmp/e2e-output.log
  exit 1
fi
