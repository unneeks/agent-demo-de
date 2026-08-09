# ADR-0010: Deliberate consolidations against the specification's entity list

**Status:** Accepted · **Date:** 2026-08-09 · **Phase:** 1

## Context

The specification and its addendum name entities to model. Taken literally, a
few would produce near-identical types that multiply the relationship
vocabulary, the schema surface and the adapter code without adding meaning.

Each departure is recorded here so it is a decision rather than an oversight.

## Decisions

### 1. `DeliveryProcess` with a `process_kind`, not three entities

The addendum lists `ReleaseProcess`, `ChangeProcess` and `IncidentProcess`.
Their fields are the same; they differ in trigger, gates and SLA. Three types
would mean three sets of relationship endpoints and three schemas, and a
fourth organizational process would need a code change.

One `DeliveryProcess` with a registry-validated `process_kind`. Kinds live in
`risk.yaml`, so adding "problem management" is a data change.

### 2. Dataset / Table / Column → one `DataAsset`

The specification lists `Dataset`, `Table` and `Column` separately. They are the
same node at different granularities: the same provenance, the same lineage
edges, the same impact semantics, differing only in what contains them.

One `DataAsset` with `asset_kind` and a self-nesting `parent_ref`. A column is a
DataAsset whose parent is a table. This keeps `DEPENDS_ON` a single edge type
rather than one per level pairing.

### 3. `Dependency` and `Lineage` → relationship types, not entities

Both are listed as entities. Both are edges with provenance, which is exactly
what ADR-0004 makes relationships. Modelling them as entities would mean an
`Entity → Dependency → Entity` triple where an edge suffices, and would put them
outside the traversal machinery.

`DEPENDS_ON` and the lineage edges are relationship types.

### 4. `Workflow` is reused, not duplicated

The addendum lists `Workflow` among delivery entities; the core metamodel
already has one. It is the same concept — an ordered set of tasks agents
participate in. Delivery reuses it and adds `delivery_task_keys`.

### 5. `Task` and `DeliveryTask` are both kept

These look duplicative and are not. `DeliveryTask` is the organization's
*template* ("Create Logical Data Model", with its checklist and gate); `Task` is
one *execution* of one, with a status, timestamps and an agent. Collapsing them
would make it impossible to ask how many times a task ran or which version of
the process it ran under. `Task.delivery_task_key` links them.

### 6. Checklist outcomes and gate assessments are value objects, not entities

`ChecklistOutcome`, `GateReadiness` and `ContractConformance` are engine results.
They are persisted (to `checklist_outcome` and `gate_assessment`) but have no
independent identity, no version, and are never referenced by other entities.
Making them entities would add three types to the enum for no queryable benefit.

## Consequences

**Good.** 66 entity types instead of ~74, a smaller relationship vocabulary, and
fewer near-duplicate schemas. Each consolidation keeps the distinction that
mattered while dropping the one that did not.

**Costs.** A reader coming from the specification will not find `Table` or
`ReleaseProcess` and needs this document to know why. `asset_kind` and
`process_kind` are string-typed and validated against registries rather than by
the type system.

**Reversible.** Each consolidation splits cleanly later if a real distinction
emerges — splitting `DataAsset` by kind would be a mechanical migration.
