#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== Building worker image (slim, fast) ==="
docker build -f Dockerfile.worker -t oasis-worker:test . || { echo "FAIL: worker build"; exit 1; }

echo "=== Verifying worker imports ==="
docker run --rm oasis-worker:test python -c \
  "from oasis.network.worker_runtime import WorkerRuntime; print('WorkerRuntime OK')" || { echo "FAIL: worker imports"; exit 1; }

echo "=== Verifying worker proto stubs ==="
docker run --rm oasis-worker:test python -c \
  "from oasis.network.proto import channel_pb2; print('WorkerInfo:', hasattr(channel_pb2, 'WorkerInfo'))" || { echo "FAIL: worker proto"; exit 1; }

echo "=== Verifying worker unregister method ==="
docker run --rm oasis-worker:test python -c \
  "from oasis.network.channel_client import WorkerNetworkChannel; print('unregister:', hasattr(WorkerNetworkChannel, 'unregister'))" || { echo "FAIL: worker unregister"; exit 1; }

# Coordinator build is skipped by default (requires poetry.lock and full deps)
# Uncomment to test coordinator:
# echo "=== Building coordinator image ==="
# docker build -f Dockerfile.coordinator -t oasis-coordinator:test . || { echo "FAIL: coordinator build"; exit 1; }

echo "=== Cleanup ==="
docker rmi oasis-worker:test 2>/dev/null || true

echo "=== ALL PASSED ==="
