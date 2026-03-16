#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SCENARIO="${1:-memory_stress}"

if command -v python >/dev/null 2>&1 && python -c "import dbt" >/dev/null 2>&1; then
  cd "${REPO_ROOT}"
  python -m simulator.dataset_generator "${SCENARIO}"
elif command -v docker >/dev/null 2>&1 && docker compose -f "${REPO_ROOT}/docker-compose.yml" ps pipeline >/dev/null 2>&1; then
  docker compose -f "${REPO_ROOT}/docker-compose.yml" exec -T pipeline python -m simulator.dataset_generator "${SCENARIO}"
else
  echo "No local Python environment detected and the Docker pipeline service is not running."
  echo "Start the stack with: docker compose -f ${REPO_ROOT}/docker-compose.yml up --build -d"
  exit 1
fi
