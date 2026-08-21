# ADR-0011: The project graph service is a thin front door, not a fourth persistence layer

**Status:** Accepted · **Date:** 2026-08-09 · **Phase:** 2

## Context

Phase 1 left every future phase addressing `persistence.ports` and `engines.*`
directly. That works for tests written against fixtures, but nothing owns "a
project's twin" as a lifecycle: nothing guarantees a relationship gets
registry-validated before it lands, nothing guarantees a write to the metadata
plane also reaches the graph plane, and nothing can answer "what did this
project's twin look like when this recommendation was made" — acceptance
criterion #19, reproducibility, had a `Project.snapshot_revision` field and no
mechanism behind it.

Phase 3 (discovery) needs somewhere to ingest facts into. Phase 6 (evaluation)
and Phase 9 (continuous PR workflow) need to query impact and gate readiness
scoped to one project without re-deriving graph plumbing each time. Both could
be solved by growing `persistence.ports` itself, or by giving each future phase
its own bespoke composition of ports and engines.

## Decision

**A new package, `project_graph/`, sitting beside `domain/`, `persistence/` and
`engines/` — not inside any of them**, because it depends on all three and none
of them should depend back on it.

**`ProjectGraphService` adds exactly four things** persistence and the engines
don't already have: registry-validated ingestion (wiring
`Relationship.validate_against`, which Phase 1 defined but no caller invoked),
dual-plane write consistency (one method writes an entity, one method writes a
relationship — metadata then graph, always both), snapshotting, and
project-scoped access to the query facade. Every write still goes through
`MetadataRepository`/`GraphRepository`; every read still returns Phase 1
entities and Phase 1 engine result types, unmodified. If a method would do
anything an engine or repository could already do unassisted, it does not
belong on the service.

**Reproducibility is content-hashed, matching the pattern `ContextBundle`
already established** rather than inventing a second hashing convention:
sort inputs, `json.dumps(sort_keys=True)`, `sha256`. A `ProjectSnapshot` pins a
version-pinned `project_ref`, a `registry_digest` (the *rules* in force, not
just the data — a snapshot can be betrayed by either changing under it), the
version-pinned entities reachable from the project node, and the relationship
ids among them. `restore_snapshot` verifies every pinned reference still
resolves *before* touching the graph plane, and fails the whole operation
loudly if anything is missing, rather than partially reconstructing state that
looks trustworthy while being wrong.

**`rebuild_graph()` takes no `project_ref`.** The literal shape considered
during planning was project-scoped, but `GraphRepository.clear()` has no
project-scoping concept — it empties the whole graph plane. A method that
accepted a `project_ref` and then cleared everyone else's data anyway would be
a worse interface than one that is honest about operating globally, from the
whole durable relationship log. Project-scoped rebuild is a real future need;
it belongs on `GraphRepository` (a `clear(scope=...)` or equivalent), not
faked at this layer.

## Consequences

**Good.** Discovery (Phase 3) has one write path with enforced invariants
instead of three future ad hoc ones. `analyze_impact`/`trace`/`assess_gate`
gain project scoping for free — the caller supplies domain objects, not
infrastructure. Reproducibility has a real, tested mechanism instead of an
unpopulated field.

**Costs.** One more layer between a caller and the ports, for callers who
genuinely need only one repository call. Nothing prevents a future caller from
going around the service and writing through the raw ports directly, skipping
registry validation and dual-plane consistency — enforcing that boundary is a
Phase 3 concern (wiring discovery adapters to call `ingest_entity` rather than
`MetadataRepository.upsert`), not something this layer can compel by itself.

**Known gap, inherited from ADR-0007.** The service is tested only against the
in-memory adapters — consistent with Phase 2's scope, since the service composes
ports it doesn't own and its correctness is fully covered by testing against
adapters already proven equivalent to the real ones by the contract suite. But
the Neo4j adapter itself remains unexecuted against a live server (ADR-0007's
"known gap"), so `rebuild_graph`, `snapshot` and `restore_snapshot` have not yet
been proven against real Neo4j traversal semantics specifically. Must be run
before a later phase depends on it under load.

## Alternatives rejected

**Grow `persistence.ports` instead.** Would mean the ports Protocol — meant to
describe what a storage adapter does — also describing project lifecycle and
snapshot semantics, which are policy above storage, not storage itself.

**Let each future phase compose its own facade.** Phase 3, 6 and 9 would each
reinvent registry validation and dual-plane consistency, with three chances to
get the invariant wrong instead of one.

**Project-scoped `rebuild_graph(project_ref)` as literally specified.** Rejected
once `GraphRepository.clear()`'s global-only semantics made the signature a
promise the implementation could not keep; see Decision above.
