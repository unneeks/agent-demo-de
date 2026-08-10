# ADR-0008: The two twins are one graph

**Status:** Accepted · **Date:** 2026-08-09 · **Phase:** 1

## Context

The Delivery Model addendum introduces a second dimension to the Project Digital
Twin: alongside the technical system, the organization's delivery process —
phases, tasks, checklists, gates, approvals, evidence.

The tempting implementation is two models with references between them: a
technical graph, a delivery graph, and a join table. It is easier to build, each
half is independently comprehensible, and different teams could own them.

It is also useless. The entire value of modelling delivery is answering
questions that *cross* the boundary: what does this code change oblige the
process to do, which gate now needs re-approval, is this architecture document
still true, where does this requirement stop being demonstrable. Every one of
those is a traversal that starts in one dimension and ends in the other.

Two models joined by a table make those queries a join-and-stitch exercise in
application code, where confidence cannot compound and provenance cannot travel.

## Decision

**One graph.** A single `EntityType` enum covering all 66 types, one
`Relationship` type, one provenance model, one graph plane, one metadata plane.

Entities carry a `twin` label of `TECHNICAL` / `DELIVERY` / `SHARED` for
navigation and reporting — a label, not a partition.

Relationship types carry a `dimension`, and **19 of 63 are `CROSS`**:

| Edge | Meaning |
|---|---|
| `GOVERNS` | which delivery task owns changes to a technical thing |
| `DESCRIBES` | a delivery artifact documents technical reality |
| `TRIGGERS_TASK` | a change creates a delivery obligation |
| `SATISFIES` | a technical test discharges an organizational control |
| `TRACED_TO` | a requirement is implemented by a delivery task |
| `PERFORMED_BY`, `PRODUCES_ARTIFACT`, `VERIFIED_BY`, `SUPPORTS_APPROVAL`, `AUTHORIZES` | the traceability chain |

## Consequences

**Good.** Impact analysis returns both dimensions from one traversal, with
confidence compounding across the twin boundary — so an obligation reached
through an inferred `DESCRIBES` reads as 0.7, not as certainty. Traceability runs
end to end. One persistence layer, one provenance model, one set of adapters.

**Costs.** A large `EntityType` enum (66) and a large relationship registry (63).
The graph roughly doubles in node count. Contributors must understand both
dimensions to add an edge type sensibly.

**Rejected consequence.** Nobody can own "just the delivery model" as a separate
service without re-fragmenting the queries that justify it.

## Alternatives rejected

**Two graphs with a join table.** Easier to build; the cross-twin questions become
application-level stitching, and confidence and provenance stop travelling.

**Delivery model as annotations on technical entities.** Cannot represent a
process that exists independently of any particular pipeline, which is what a
delivery model is.
