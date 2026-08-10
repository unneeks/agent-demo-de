#!/usr/bin/env bash
set -e

# Change directory to the script's parent folder (agentic-data-engineering)
cd "$(dirname "$0")/.."

echo "Setting up Python virtual environment..."
python3.12 -m venv .venv
source .venv/bin/activate

echo "Installing dependencies..."
pip install --upgrade pip setuptools build
pip install -e ".[dev,web,agent,neo4j,postgres]"

echo "Setting up unified AI assistant rules (Gemini, Claude, Copilot)..."
# Link Antigravity/Gemini rule file to CLAUDE.md
rm -f AGENTS.md
ln -s CLAUDE.md AGENTS.md

# Link GitHub Copilot rule file to CLAUDE.md
mkdir -p .github
ln -sf ../CLAUDE.md .github/copilot-instructions.md

echo "Setup complete! All AI assistants now share CLAUDE.md."
