# Graph Model — the Dual Digital Twin

The graph plane answers one family of questions: *what is connected to what, how
certainly, and how far*. Impact analysis, delivery obligations, traceability and
lineage are all traversals over it.

## Node model

```cypher
(:Entity {entity_type: "Pipeline", entity_id: "stg_bank_customers", twin: "TECHNICAL"})
```

**Nodes are not versioned.** A node is the thing itself; versioned state lives in
PostgreSQL. Versioning the graph would fragment the twin into one island per
release. Node lookups therefore return unversioned `EntityRef`s — asserted by
`test_neighbors_return_unversioned_identities`.

## Edge model

All edges use the Neo4j type `:RELATES`, with the real type in a `rel_type`
property:

```cypher
(s:Entity)-[:RELATES {rel_type: "DESCRIBES", provenance: "INFERRED", confidence: 0.7,
                      source_document: "Handbook.pdf", dimension: "CROSS"}]->(t:Entity)
```

Unidiomatic and deliberate. Cypher cannot parameterize relationship types, so
native typing would mean interpolating a registry-supplied string into query
text on every write — an injection surface, and a guarantee that adding a
relationship type to YAML also requires new code. Filtering on an indexed
property costs little and keeps the vocabulary in data (ADR-0004).

Constraints require `rel_type`, `provenance` and `discovered_at` on every edge:
an edge that cannot say how it came to be believed is not admissible.

## The twin

```
                    TECHNICAL                            DELIVERY

Repository                                          DeliveryModel
   │ CONTAINS                                          │ HAS_PHASE
   ▼                                                   ▼
CodeArtifact ◀── DEPENDS_ON ── Pipeline           DeliveryPhase
                                  │  ▲                 │ HAS_TASK
                        DEPENDS_ON│  │GOVERNS ─────────┤
                                  ▼  │                 ▼
                              DataAsset            DeliveryTask
                                  ▲                 │  │  │
                           COVERS │      VALIDATED_BY│  │  │ENDS_AT_GATE
                                  │                  ▼  │  ▼
                                Test              Checklist  ApprovalGate
                                  │                            ▲
                          SATISFIES│                            │
                                  ▼                             │
                        EvidenceRequirement                     │
                                                                │
   Evidence ──────── SUPPORTS_APPROVAL ────▶ Approval ──────────┘
                                                 │ AUTHORIZES
                                            Deployment
```

**Edge direction convention:** an edge points from the dependent to what it
depends on. `Pipeline DEPENDS_ON DataAsset` means the pipeline reads the asset.
Walking *incoming* edges from a changed node therefore finds everything
downstream, which is why `traverse()` defaults to `direction="incoming"`.

## Confidence-weighted traversal

Confidence multiplies along the path:

```
raw.customers ◀──DEPENDS_ON(0.8)── stg ◀──DEPENDS_ON(0.8)── mart
                       1 hop: 0.8                    2 hops: 0.64
```

Structural edges carry no confidence and count as certain. When a node is
reachable several ways the most confident path wins. `min_confidence` prunes
speculative reach, and each result carries the ordered `path` of relationship
types — because an impact claim has to be able to show its working.

This matters most on cross-twin edges. A `DESCRIBES` edge at 0.6 means the
platform is not sure that document is about that pipeline, and telling someone
to update it as though it were certain is how the tool gets ignored.

## Rebuilding

The graph plane is a projection; `metamodel_relationship` in PostgreSQL is the
durable log:

```python
graph.clear()
for edge in postgres.all_relationships():
    graph.upsert_relationship(edge)
```

Asserted by `test_graph_is_rebuildable_from_stored_relationships`. This is what
keeps the graph store replaceable.

## Indexes

| Index | Why |
|---|---|
| `entity_identity` (unique) | Node identity; makes `MERGE` correct and fast |
| `entity_type_index` | "All pipelines in this project" |
| `entity_twin_index` | Scope a query to one dimension without listing types |
| `rel_type_index` | Every traversal filters on it |
| `rel_confidence_index` | `min_confidence` pruning before the walk |
| `rel_dimension_index` | Cross-twin edges are queried as a set |

## Applying the schema

```bash
docker compose up -d neo4j
cat persistence/neo4j/constraints.cypher | cypher-shell -u neo4j -p devpassword
```

Or from Python, idempotently: `Neo4jGraphRepository(...).apply_constraints()`.
