#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SCENARIO="${1:-memory_stress}"

docker compose -f "${REPO_ROOT}/docker-compose.yml" up --build -d ollama agent pipeline
"${REPO_ROOT}/scripts/setup.sh"
"${REPO_ROOT}/scripts/load_dataset.sh" "${SCENARIO}"
docker compose -f "${REPO_ROOT}/docker-compose.yml" up -d sensor

echo "Closed-loop demo started."
echo "Watch live logs with:"
echo "  docker compose -f ${REPO_ROOT}/docker-compose.yml logs -f pipeline sensor"
