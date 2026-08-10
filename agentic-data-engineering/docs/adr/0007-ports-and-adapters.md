# ADR-0007: Ports and adapters with an in-memory reference implementation

**Status:** Accepted · **Date:** 2026-08-09 · **Phase:** 1

## Context

The platform must survive its own dependencies being replaced. There is also a
practical concern: a foundation whose tests require `docker compose up` gets a
slow feedback loop, and the metamodel is the worst place to accept friction.

The usual answer — mock the database — trades one problem for another. Mocks
encode unverified assumptions about the real store and drift.

## Decision

**Ports are Protocols**, structurally typed and `runtime_checkable`. Nothing above
the persistence layer imports an adapter.

**Three adapters per plane, one contract.** `tests/contract/` is parameterized
across all of them. Real-store variants skip cleanly when unreachable, detected
by a fast TCP probe rather than a driver timeout.

**The in-memory adapter is the reference implementation, not a mock.** It is held
to the identical contract, so when a real adapter's behaviour is ambiguous, this
is the specification. Being a real implementation, it cannot drift silently.

**Optional drivers import lazily**, so the whole unit suite runs without extras.

**Static conformance runs everywhere.** `tests/unit/test_ports.py` compares method
names and signatures against the Protocol, catching drift in adapters that
cannot be executed in a given environment.

## Consequences

**Good.** 335 unit tests run in under a second with no infrastructure. Storage is
genuinely replaceable. The two-plane split is enforced by the ports rather than
by convention.

**This has already paid.** Running the contract suite against real PostgreSQL
exposed a test-isolation defect — the append-only `audit_ledger` was never
truncated between runs, so state leaked across pytest invocations. No in-memory
test could have found it.

**Costs.** Contract changes must be made in three places. The in-memory adapter is
real code with real bugs. Transaction isolation and concurrency remain covered
only when the real store runs.

**Known gap.** The Neo4j adapter is unexecuted: the build sandbox had no Docker
daemon and the Neo4j distribution was proxy-blocked. It passes static conformance
and its Cypher deliberately mirrors in-memory semantics
(`coalesce(confidence, 1.0)`), but it must be run against a live server before
Phase 2 depends on it.

## Alternatives rejected

**Mocks.** Verify nothing about the real store while drifting from it.

**Real infrastructure for every test.** Unusable feedback loop; no test run
without Docker.
