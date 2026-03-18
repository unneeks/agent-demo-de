# SignalLayer

SignalLayer is a browser-based conversation augmentation MVP for WhatsApp Web. It overlays non-intrusive annotations, tooltips, and a right-side analysis pane while keeping original message content untouched.

## What is included

- Chrome extension content script with inline badges and a summary bar
- React component system for tooltip and sidebar analysis
- Node backend with `/analyze` and `/health`
- Modular reasoning pipeline:
  1. claim extraction
  2. classification
  3. RAG-lite retrieval
  4. counterpoint generation
  5. confidence scoring
- Prompt-generation registry and architecture spec
- Tests for parser robustness and backend contracts

## Run

```bash
cd /Users/ranjitpillai/codexmap/signallayer
npm run build
npm run backend
```

Load the unpacked extension from:

`/Users/ranjitpillai/codexmap/signallayer/extension/dist`

Then open WhatsApp Web and keep the backend running at `http://localhost:8787`.

## Files by phase

- Architecture: `docs/architecture.json`, `docs/architecture.md`
- Prompt registry: `docs/prompt-registry.json`, `shared/prompts.js`
- Backend: `backend/src`
- Extension: `extension/src`
- Tests: `backend/tests`, `tests`
