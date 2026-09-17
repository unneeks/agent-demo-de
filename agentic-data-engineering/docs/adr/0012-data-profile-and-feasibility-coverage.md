# ADR-0012: DataProfile as a first-class entity; feasibility assessment closed as registry data

**Status:** Accepted · **Date:** 2026-08-09 · **Phase:** 2

## Context

A review of the worked delivery model against real delivery activities, done
before Phase 2's service layer, found three gaps between what the metamodel
represents and what data engineering delivery actually does:

1. **Data profiling** was named only as a bare skill string
   (`data-profiling`), never declared as a `Capability`, and had nowhere to
   store a structured result — a profiling run's row counts, null rates and
   distinct counts had no entity to live on.
2. **Feasibility assessment** did not exist anywhere in the metamodel or
   registries, despite being a standard discovery-phase activity ("can this be
   built, at what cost, with what risk") distinct from both requirements
   management and architecture.
3. **Conceptual modeling** was only ever an *input* — `task.logical-data-model`
   declared `in.conceptual-model` — but nothing in the worked model *produced*
   it. The input could never be satisfied.

Two of the three are pure registry data (ADR-0002: vocabularies are YAML, not
code). Data profiling needed one new entity.

## Decision

**`DataProfile`, a new `ProvenancedEntity` on the technical twin**
(`domain/metamodel/entities/technical/profile.py`), modeled explicitly parallel
to `SchemaDefinition`: `asset_ref` (what was profiled), `metrics: dict[str,
float]` (free-form, the same reasoning as `Observation.metrics` — profiling
metrics vary by column type, a rigid schema would fight every real profiling
tool's actual output), `profiled_at`, `sample_size`. Kept as its own entity
rather than a field on `DataAsset`, for the same reason `SchemaDefinition` is
kept separate from `DataAsset`: profiling results need to be structured and
comparable *over time*, so drift is a first-class, queryable fact rather than
an overwritten value. A new `PROFILES` relationship type
(`DataProfile → DataAsset`) links a profile to what it profiled.

**`feasibility-assessment` closed entirely as registry data**: a
`DeliveryCapability` (category `definition`), an `EngineeringResponsibility`
(`resp.feasibility-assessment`, delegable to an agent for the assessment
itself), a discovery-phase `DeliveryTask` producing a `DeliveryArtifact`, a
4-item checklist, and two acceptance criteria.

**No non-delegable `resp.feasibility-signoff` twin was added**, unlike the
assessment/sign-off pairs ADR-0009 established for security and release. The
discovery phase in the worked model has no `ApprovalGate` for a non-delegable
responsibility to hang authority on — feasibility assessment feeds the GO /
NO-GO / CONDITIONAL decision recorded directly on the artifact, not a gate
decision. Adding a signoff responsibility with no gate to attach it to would
have been authority in name only. If a future revision of the worked model adds
a discovery-phase gate, this is the place to reconsider.

**`task.conceptual-model` added to the architecture phase**, producing the
`DeliveryArtifact` (`artifact_kind: conceptual-model`) that
`task.logical-data-model`'s existing `in.conceptual-model` input already
expected — closing the gap where that input could never be satisfied by
anything in the worked model.

**`task.data-profiling` added to the testing phase**, producing a
`DataProfile` per profiled asset, feeding `resp.data-correctness` /
data-quality-assurance, mirroring `task.data-quality-rules`'s existing shape
(no checklist — not every task needs one).

## Consequences

**Good.** Profiling drift ("this column's null rate moved from 2% to 40%
between runs") is now a comparison over time, not a value silently overwritten.
Feasibility assessment is now assessable by an agent and traceable to a
delivery capability, a responsibility and a checklist, the same as every other
discovery-phase activity. The `in.conceptual-model` input is satisfiable.

**Costs.** One more entity type (68th) and one more relationship type (64th)
to keep in the schema-export and registry-validation drift checks. The worked
model grew from 10 tasks/5 checklists/8 criteria/5 gates to 13 tasks/6
checklists/10 criteria/6 gates (the gate count grew from the separate
`approves_gate_keys` fix in the same round, not from this work — see the
registry-validation fix landed alongside it).

## Alternatives rejected

**`DataProfile` as a field on `DataAsset`.** Rejected for the same reason
`SchemaDefinition` was already kept separate: a field only ever holds the most
recent value, and profiling's entire value is in comparing runs.

**A non-delegable `resp.feasibility-signoff` regardless of the missing gate.**
Rejected as authority with nothing to enforce it — see Decision above.

**Extending `task.data-quality-rules` instead of a new `task.data-profiling`
task.** Rejected because data-quality *rules* (constraints, expectations) and
data *profiling* (descriptive statistics) are different activities that happen
to feed the same downstream responsibility; conflating them would make "did we
profile this asset" and "did we define quality rules for it" the same
unanswerable question.
