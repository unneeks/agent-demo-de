#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
OLLAMA_MODEL="${OLLAMA_MODEL:-llama3.2:3b}"

if command -v docker >/dev/null 2>&1 && docker compose -f "${REPO_ROOT}/docker-compose.yml" ps ollama >/dev/null 2>&1; then
  echo "Pulling model into the Docker Compose Ollama service: ${OLLAMA_MODEL}"
  docker compose -f "${REPO_ROOT}/docker-compose.yml" exec -T ollama ollama pull "${OLLAMA_MODEL}"
else
  echo "Pulling model with the local Ollama CLI: ${OLLAMA_MODEL}"
  ollama pull "${OLLAMA_MODEL}"
fi
