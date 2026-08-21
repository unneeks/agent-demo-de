# ADR-0001: Two-plane persistence — PostgreSQL for state, Neo4j for traversal

**Status:** Accepted · **Date:** 2026-08-09 · **Phase:** 1

## Context

The platform stores two different kinds of metadata. Configuration and state —
agent versions, contracts, gate assessments, approvals, the audit ledger — needs
transactions, exact lookups, version history, and an audit trail that cannot be
quietly rewritten. The dual digital twin needs something else: multi-hop
traversal with per-edge confidence, which in SQL means recursive CTEs that get
slower and less readable as the twin grows. With two twins joined by 19
cross-twin edge types, the traversal load roughly doubles.

One store for both means one job done badly.

## Decision

**PostgreSQL — metadata plane. System of record for entity _state_.** Versioned
entity rows for both twins (JSONB payload with identity, version, type and twin
promoted to columns), the durable relationship log, gate assessments, checklist
outcomes, context bundles, and an append-only hash-chained audit ledger.

**Neo4j — graph plane. System of record for relationship _traversal_.** The dual
twin: nodes keyed by `(entity_type, entity_id)`, provenanced edges.

**The graph plane is a projection.** Relationships are written durably to
`metamodel_relationship` as well, so the twin can be dropped and rebuilt.

Nodes carry no version. Both planes are reached only through Protocols in
`persistence/ports.py`, each with an in-memory implementation held to the same
contract suite.

## Consequences

**Good.** Each store does what it is good at. Rebuildability makes the graph
genuinely replaceable. Reproducibility is achievable because the durable copy is
transactional. The unit suite needs no infrastructure.

**Costs.** Two stores to operate; relationships written twice. Writes are not
atomic across planes, so the graph can lag — acceptable precisely because it is
rebuildable, and a reconciliation job can repair drift later.

**Risk accepted.** Adapters can drift. Mitigated by one contract suite across all
of them plus static signature conformance. This has already paid: running the
suite against real PostgreSQL exposed a test-isolation defect the in-memory
adapter could not surface.

## Alternatives rejected

**PostgreSQL only.** Traversal becomes the hardest code in the system, and
confidence-weighted variable-depth walks across two twins are what the platform
does most.

**Neo4j only.** Weaker transactional guarantees for the ledger, and no natural
home for a database-enforced append-only hash chain.
