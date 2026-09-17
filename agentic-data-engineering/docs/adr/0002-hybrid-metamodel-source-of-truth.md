# ADR-0002: Hybrid source of truth — Pydantic shapes, YAML vocabularies

**Status:** Accepted · **Date:** 2026-08-09 · **Phase:** 1

## Context

"Metadata first" pulls toward making everything declarative. Type safety, IDE
support and testable validation pull the other way. Fully declarative means
dynamic objects, no static checking, and a lot of machinery before anything
works. Fully typed means adding a capability — or a whole delivery model — is a
code change, review and release, which is exactly the coupling the principle
exists to prevent.

The addendum sharpens this. An organization's delivery model *must* be data: it
differs per organization, changes without notice, and will eventually be
produced by an extraction pipeline rather than by hand.

## Decision

Split by what changes and how often.

**Entity shapes are Pydantic v2 models.** All 66 entity types. JSON Schema is
generated and committed with a drift check. Shapes change rarely and their
invariants — provenance, blocking rules, lifecycle, waiver attribution — are
logic that belongs in code where it can be tested.

**Vocabularies are versioned YAML.** Capability catalogs (both kinds), the
four-level role chain, relationship types with permitted endpoints, platform
bindings, provenance rules, the approval matrix, delivery process kinds, and
**entire delivery models** under `delivery-models/`.

`registry.py` loads and cross-validates, reporting every problem at once.

The halves are pinned together by a test comparing `METAMODEL_VERSION` with the
registry version.

## Consequences

**Good.** A new organization's delivery model is a YAML file. Adding a capability,
role or relationship type is a data change. Entity invariants stay statically
checked. JSON Schema comes free.

**Costs.** Two places to look; mitigated by `metamodel-spec.md` stating the split.
The registry loader is hand-written code that must track the YAML shape — the
largest single file in the domain layer, and the price of the flexibility.

**Deliberate asymmetry.** Adding an entity type is heavier than adding a delivery
model. That is the intended signal.

## Alternatives rejected

**Pure Pydantic.** Every delivery model becomes a code change — untenable once
models are extracted from customer documentation.

**Pure declarative.** No static typing, and all the entity invariants end up in a
hand-rolled rule engine rather than tested code.
