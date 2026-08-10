# ADR-0003: Four-state provenance with document attribution

**Status:** Accepted · **Date:** 2026-08-09 · **Phase:** 1

## Context

A platform that reads a brownfield project produces two kinds of statement that
look identical once written down: "this dbt model reads `raw.customers`" (read
from a manifest) and "this table is probably related to that one" (guessed from
a naming convention).

The Delivery Twin makes this far worse. Delivery metadata is extracted from
prose — handbooks, Confluence, PDFs — so almost everything in it is an
interpretation. "Architecture review must be completed before development
begins" is one sentence; turning it into a phase dependency, a gate and a
required role is four inferences, each fallible.

The usual mitigation is an optional `confidence` column that is frequently
`None` and never enforced.

## Decision

Four states with invariants enforced at construction:

| State | Enforced requirement |
|---|---|
| `OBSERVED` | `discovered_by` required; confidence pinned to 1.0 |
| `INFERRED` | **`confidence` required** |
| `HUMAN_VERIFIED` | `human_verified_by` required, timestamped |
| `CERTIFIED` | `human_verified_by` required, timestamped |

Plus **document provenance** on every provenanced entity: `source_document`,
`source_section`, `extraction_method`. `SEMANTIC_EXTRACTION` requires a source
document — an unattributable reading of a document cannot be checked.

Enforced in three places: the `Provenanced` validator, PostgreSQL `CHECK`
constraints, and `provenance.yaml` which declares what each state permits.

Specifically rejected: `OBSERVED` with confidence ≠ 1.0. Doubt means it was
inferred.

## Consequences

**Good.** Inference cannot masquerade as fact anywhere. Every extracted delivery
rule cites the paragraph it came from. Traversal multiplies confidence and gives
a calibrated answer. Automated action can be gated on provenance rank.

**Costs.** Ten extra fields on every discovered entity. Extraction adapters must
decide, for every fact, whether they saw it or concluded it — friction, and the
point. `CHECK` constraints duplicate Python rules deliberately.

**Rejected as too weak.** A single optional `confidence: float | None`. It cannot
distinguish "certain" from "nobody filled this in".
