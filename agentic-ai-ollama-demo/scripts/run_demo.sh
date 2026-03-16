#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROMPT="${1:-Why did the nightly ETL pipeline fail?}"

if command -v python >/dev/null 2>&1 && python -c "import fastapi, langgraph" >/dev/null 2>&1; then
  cd "${REPO_ROOT}"
  python -m agent.main "${PROMPT}"
elif command -v docker >/dev/null 2>&1 && docker compose -f "${REPO_ROOT}/docker-compose.yml" ps agent >/dev/null 2>&1; then
  docker compose -f "${REPO_ROOT}/docker-compose.yml" exec -T agent python -m agent.main "${PROMPT}"
else
  echo "No local Python environment detected and the Docker agent service is not running."
  echo "Start the stack with: docker compose -f ${REPO_ROOT}/docker-compose.yml up --build"
  exit 1
fi
