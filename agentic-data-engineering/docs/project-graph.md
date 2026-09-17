# The Project Graph Service

Phase 1 built a durable core addressed directly against `persistence.ports` and
`engines.*` — but nothing owned "a project's twin" as a lifecycle. Every future
phase needs one: discovery has to ingest facts into *something*; evaluation and
the continuous PR workflow need to query impact and gate readiness *scoped to a
project* without re-deriving graph plumbing each time; and acceptance criterion
#19 (reproducibility) needed an actual snapshot operation, not just a
`Project.snapshot_revision` field nothing populated.

`ProjectGraphService` (`project_graph/service.py`) is that missing layer.

## The one idea that must not be compromised

**A thin, disciplined front door — not a fourth persistence layer.** Every write
still goes through `MetadataRepository`/`GraphRepository`; every read still
returns Phase 1 entities and Phase 1 engine result types unchanged. The service
adds exactly four things persistence and the engines don't already have on their
own:

1. **Registry-validated ingestion** — `Relationship.validate_against()` existed
   in Phase 1 but no calling code ever invoked it. `ingest_relationship` is
   where it finally gets wired in.
2. **Dual-plane write consistency** — metadata and graph together, never one
   without the other, because there is exactly one method that writes an entity
   and exactly one that writes a relationship.
3. **Snapshotting** — a reproducible, content-hashed, point-in-time view of a
   project's twin, and its exact inverse, restore.
4. **Project-scoped access to the query facade** — a caller supplies domain
   objects (a `Change`, a `Requirement` ref, a `Gate` + `GateState`), not a
   `GraphRepository`.

If a method here does anything an engine or a repository could already do
unassisted, it does not belong here.

## Lifecycle

```python
from project_graph import ProjectGraphService

service = ProjectGraphService(metadata_repo, graph_repo)

service.register_project(project)                    # first write
service.ingest_entity(pipeline)                       # any entity, any phase
service.ingest_relationship(edge, registry)           # validates, then writes both planes
service.rebuild_graph()                               # graph <- durable relationship log
```

`ingest_relationship` validates before writing anything. A relationship whose
endpoint types the registry does not permit, or an `INFERRED` edge on a
provenance-requiring type with no confidence score, raises `IngestionError` —
and neither plane is touched. A partial write is worse than no write: it would
mean the two planes silently disagree about what exists.

`rebuild_graph()` proves ADR-0001's "the graph plane is a projection" claim with
working code: it clears the graph plane and repopulates it from
`MetadataRepository.all_relationships()`, the durable log. It takes no
`project_ref` — `GraphRepository.clear()` has no project-scoping concept, so a
project-scoped rebuild would need to pretend to isolate one project's slice of a
graph the port itself treats as one whole. Rebuilding globally, honestly, beats
a signature that promises scoping the underlying store cannot deliver.

## Snapshot and restore

A snapshot pins the transitive closure of a project's graph node — walked in
both directions, up to `max_depth` — together with the registry's rule surface
at capture time:

```python
snapshot = service.snapshot(project_ref, registry)
# ProjectSnapshot(
#   project_ref=Project:demo@0.1.4,       # version-pinned
#   registry_digest="a3f9...",            # the *rules* in force, not just the data
#   entity_refs=[...],                    # every reachable entity, version-pinned
#   relationship_ids=[...],               # every edge with both endpoints reachable
#   snapshot_hash="7c2e...",
# )
```

Only nodes that also have a row in the metadata plane are pinned into
`entity_refs`. A node reached through traversal with no metadata row is a
catalog or registry reference — an `EngineeringRole`, a `Capability`
definition, a `DeliveryTask` template — not project-owned instance data, and
those are already covered as a whole by `registry_digest` rather than pinned
individually.

`registry_digest` matters because a snapshot can be betrayed two ways: the
*data* changing under it, or the *rules* changing under it. Pinning entity
versions catches the first. Hashing the registry's capability, role and
relationship-type keys catches the second — the same reasoning ADR-0011 records
for reusing the context assembler's hashing pattern rather than inventing a
second one.

`restore_snapshot` is the exact inverse, and it fails loudly rather than
quietly:

```python
service.restore_snapshot(snapshot)
```

Before touching the graph, it checks that every pinned entity and every pinned
relationship still exists in the metadata plane. If anything pinned has since
been deleted, it raises `SnapshotError` and leaves the graph plane untouched. A
snapshot that quietly restores only part of what it pinned is worse than one
that refuses, because it looks trustworthy while being wrong. Only after every
check passes does it clear the graph and rebuild from the pinned entities and
the pinned relationship ids *only* — never whatever relationships exist now,
because the whole point is reconstructing what existed *then*.

Two snapshots of identical state, built by walking entities and edges in a
different order, hash identically — `compute_snapshot_hash` sorts before
hashing, the same way `ContextBundle.bundle_hash` does in
`engines/context/assembler.py`.

## Query facade

Three thin wrappers over the Phase 1 engines, project-scoped because they close
over the service's own `GraphRepository`:

```python
service.analyze_change(change, delivery_model)   # -> ChangeImpact
service.trace_requirement(requirement_ref)        # -> TraceabilityChain
service.assess_readiness(gate, gate_state)         # -> GateReadiness
```

None of these alter engine semantics — `tests/unit/test_project_graph.py`
asserts each call matches calling `engines.impact.analyze_impact`,
`engines.impact.trace` and `engines.gates.assess_gate` directly. The value is
composition, not new logic: one import instead of three, and a caller that
never needs to know the service holds a `GraphRepository` at all.

`GateState` is still assembled by the caller. The service does not synthesize
checklist outcomes or approvals from nothing, since nothing upstream of the
evaluation/runtime phases produces those yet.

## Errors

| Error | Raised when |
|---|---|
| `UnknownProjectError` | An operation names a `project_ref` that was never `register_project`-ed |
| `IngestionError` | An entity's type isn't registered in `ENTITY_CLASSES`, or a relationship fails `validate_against` |
| `SnapshotError` | `restore_snapshot` finds a pinned entity or relationship no longer in the metadata plane |

Each wraps the underlying failure with the context a caller actually needs —
which project, which operation, which reference — rather than letting a raw
Pydantic or registry error surface unadorned.

## What this is not

Not a fourth persistence layer, not an orchestrator, not a discovery pipeline.
It composes ports it doesn't own, over data no phase after this one is required
to route through it — Phase 3's discovery adapters *should* write through
`ingest_entity`/`ingest_relationship` rather than the raw ports, because that's
where registry validation and dual-plane consistency live, but nothing about
the service prevents a future caller from going around it. Enforcing that is a
Phase 3 concern, not this one's.
