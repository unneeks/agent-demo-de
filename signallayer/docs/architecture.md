# SignalLayer Architecture

## Overview

SignalLayer is split into five explicit subsystems so we can keep the extension responsive while moving deeper reasoning into the backend:

1. Extension Layer
2. UI Component Layer
3. Backend Layer
4. AI Agent Layer
5. Data Layer

The runtime path is:

`WhatsApp DOM -> parser -> fast pass badges -> backend analyze -> structured response -> tooltip/sidebar update`

## Subsystem Notes

### Extension Layer

The extension owns DOM observation, message extraction, cache-aware request scheduling, and event wiring. It never mutates the original message text. Instead, it appends isolated overlay nodes next to messages and mounts a separate fixed sidebar host on the page edge.

### UI Component Layer

The UI layer renders SignalLayer state into dark-theme cards and badges using a host-isolated container. It supports progressive disclosure:

- badge for quick signal
- tooltip for glanceable summary
- sidebar for full claim and evidence review

### Backend Layer

The backend exposes a stable `/analyze` contract and keeps orchestration deterministic. It runs a fast classifier immediately and a deeper pipeline for structured claim output, with cache lookup keyed by `messageHash`.

### AI Agent Layer

The reasoning layer is modular:

1. claim extraction
2. classification
3. retrieval
4. counterpoint generation
5. confidence scoring

This avoids a single opaque prompt and lets the UI explain what the system is doing.

### Data Layer

The data layer is intentionally lightweight for MVP: shared schemas, small evidence corpus, normalization helpers, and an in-memory cache. It is designed to upgrade later to vector search or external storage without changing the extension contract.

## Primary Failure Strategy

When something goes wrong, the system degrades visibly but safely:

- selector drift: stop annotating and keep host UI intact
- backend failure: show warning badge and retry affordance
- no claims: show neutral state rather than inventing analysis
- conflicting evidence: lower confidence and surface both sides

## MVP Layout

- `signallayer/extension`: Chrome extension overlay and React-based UI mount
- `signallayer/backend`: Node HTTP API and reasoning pipeline
- `signallayer/shared`: contracts, prompt engine, corpus, utilities
- `signallayer/tests`: DOM fixtures and integration-oriented tests
