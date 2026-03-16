# ARCHITECTURE

## Current Baseline

The repository starts with a dependency-light browser application so the domain
model and visualization vocabulary can stabilize before introducing framework
and infrastructure complexity.

### Layers

1. `src/data`
   - Seed records only
   - Later replaced by generated artifacts from a curated source pipeline
2. `src/domain`
   - Pure functions for validation, timeline calculations, and query parsing
   - Intended to remain framework-agnostic
3. `src/main.js`
   - Thin UI composition layer for the current prototype
   - Hosts a small visualization registry so new views can be added without
     rewriting query and selection flows
4. Root documentation files
   - Persistent project memory for roadmap, limitations, architecture, and tasks

## Target Evolution

### Frontend

- Migrate UI to React or Next.js when multiple coordinated views exist
- Use D3 for timeline and network layout logic
- Use Deck.gl or map rendering once region geometry is added
- Preserve a shared visualization contract across views:
  - input: filtered traditions
  - output: selectable marks
  - side effect: one shared detail panel

### Backend

- Add a content pipeline that validates source-cited tradition records
- Introduce a graph-oriented API for influence edges and query results
- Add PostGIS-ready region storage when map views become active

### Data

- Move from embedded arrays to normalized entities:
  - `traditions`
  - `influence_edges`
  - `regions`
  - `events`
  - `sources`

## Architectural Constraints

- Keep domain logic independent from rendering code.
- Add new views without mutating the core schema ad hoc.
- Avoid historical claims without provenance.
- Prefer append-only migrations for data model changes.
