# ADR-0004: Relationships are first-class objects with a data-driven vocabulary

**Status:** Accepted · **Date:** 2026-08-09 · **Phase:** 1

## Context

The obvious representation of "this pipeline depends on that table" is a foreign
key. It is cheap, and it discards who discovered it, from what evidence, whether
it was seen or guessed, and how confident they were — all of which are
properties of the *edge*.

The dual twin makes this decisive. "This architecture document describes this
pipeline" is almost always an inference, and an impact analysis that treats it
as certain will tell someone to update a document that was never about their
code. The confidence has to live on the edge.

Second problem: if the legal edge types live in code, extending the graph
vocabulary is a code change — for the part of the metamodel most likely to grow,
since every new organization brings new delivery relationships.

## Decision

**Relationships are objects.** `Relationship` carries `source`, `target`, `type`
and the full `Provenanced` mixin including document attribution. Natural key is
`(source, type, target)` on identity refs.

**The vocabulary is data.** 63 types in `relationship_types.yaml`, each declaring
permitted endpoints, cardinality, whether provenance is required, and a
`dimension` of `TECHNICAL` / `DELIVERY` / `CROSS` / `SHARED`.

**Validation is explicit**, not in the constructor, so an edge written under an
older registry version can still be deserialized and inspected.

**Structural edges are exempt from provenance** — `Agent HAS_SKILL Skill` is a
declaration, not a discovery.

## Consequences

**Good.** An inferred `DESCRIBES` is visibly different from an observed
`DEPENDS_ON`. Traversal can prune speculation. Every impact claim shows its path.
New edge types cost a YAML entry. The `CROSS` dimension makes the twin join
queryable as a set.

**Costs.** More storage per edge and more ceremony to create one — mitigated by
the `relationship()` helper. Validation being separate means a caller can forget
it; the registry suite covers the vocabulary itself.

**Consequence for Neo4j.** Because the type is data, every edge is stored as
`:RELATES` with `rel_type` indexed. Native types would require interpolating a
registry string into Cypher on every write.

## Alternatives rejected

**Foreign-key lists.** Cheapest, loses provenance — the one thing this platform
cannot afford to lose.

**A relationship enum in code.** Keeps type safety, makes the vocabulary a code
change and scatters endpoint rules across validators.
