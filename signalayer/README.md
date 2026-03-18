# SignalLayer

SignalLayer is a standalone browser chat app that augments conversations with:

- inline message badges
- hover-level quick insights
- a right-side analysis pane
- conversation summary telemetry
- claim extraction and reasoning

The MVP in this repo is organized as:

- `signalayer/docs`: architecture and prompt artifacts
- `signalayer/backend`: analysis API, reasoning pipeline, retrieval, cache
- `signalayer/frontend`: React chat app with annotation UI
- `signalayer/tests`: backend and integration-style tests

This implementation intentionally replaces the WhatsApp overlay dependency with a first-party chat surface while preserving the same augmentation workflow.

## Run

From `/Users/ranjitpillai/codexmap/signalayer`:

```bash
npm install
npm run dev:backend
```

In a second terminal:

```bash
npm run dev:frontend
```

Open `http://localhost:4174`.

## Test

```bash
npm test
npm run build
```

## Key files

- Architecture: `/Users/ranjitpillai/codexmap/signalayer/docs/architecture.json`
- Prompt registry: `/Users/ranjitpillai/codexmap/signalayer/docs/prompt-registry.json`
- Backend API: `/Users/ranjitpillai/codexmap/signalayer/backend/src/server.js`
- Analysis pipeline: `/Users/ranjitpillai/codexmap/signalayer/backend/src/ai/pipeline.js`
- Frontend app shell: `/Users/ranjitpillai/codexmap/signalayer/frontend/src/App.jsx`
