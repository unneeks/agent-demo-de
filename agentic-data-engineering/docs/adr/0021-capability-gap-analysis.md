# ADR-0021: Capability gap analysis, with coarse automatic maturity inference

**Status:** Accepted · **Date:** 2026-08-10 · **Phase:** —

## Context

ADR-0020 wired the `conformance_of()` half of the original spec's
Composition Engine line but explicitly deferred the other half: "given a
project's **capability gaps**, resolves which Engineering Roles are
needed." No code anywhere constructed a `Capability`/`DeliveryCapability`/
`CapabilityGap` instance for a real project, and the registry had no
"desired maturity" data to compare an observed one against.

**Scope, per explicit user decisions:** (1) attempt automatic maturity
inference rather than caller-supplied-only — the harder, more valuable
option, grounded in a verified finding: `metamodel-registry/capabilities
.yaml`'s `detection_hints` and `delivery_capabilities.yaml`'s
`realized_by_roles` were both already loaded into `MetamodelRegistry
.capabilities`/`.delivery_capabilities` (`CapabilitySpec`) and never
consumed anywhere — the same "metamodel anticipated this, nothing built
it" shape `conformance_of()`/`contract_for()` were in before ADR-0020. (2)
wire into `orchestrator/cycle.py::run_cycle()` as a new optional step,
alongside OBSERVE/DETECT CHANGE+IMPACT/SELECT AGENTS/EVALUATE/APPROVAL
GATE.

**A finding that shaped the design, verified directly:**
`ProjectGraphService.assess_readiness()`/`GateReadiness` could not be
reused as the delivery-capability maturity signal. Its own docstring
states four of `GateState`'s six dimensions (`present_artifact_kinds`,
`checklist_outcomes`, `satisfied_evidence`, `approvals`) "have no real
assembler anywhere in this codebase" — a deliberate, already-documented
gap (`docs/orchestrator.md`'s "what this is not"). Using full
`GateReadiness.status` here would have silently laundered that gap into a
new engine, reporting artificially healthy maturity. Delivery-capability
maturity therefore uses only the one honestly-computable signal that ties
to a specific capability: real, persisted `Evaluation`s against the
capability's governing `DeliveryContract`s (`EVALUATES` already permits
`DeliveryContract` as a subject, per `relationship_types.yaml`).

## Decision

**`engines/gap_analysis/`, a new pure package**, mirroring the existing
engines' no-I/O discipline:

- `inference.py::infer_technical_maturity()` — 0 if no `Pipeline`'s
  `pipeline_kind`/`orchestrator`/`source_path` matches a
  `detection_hint`; else 1-4, scaling with the fraction of matching
  pipelines a `Test.covers_refs` actually covers. Never 5.
- `inference.py::infer_delivery_maturity()` — 0 if the capability governs
  no task with a real `DeliveryContract`, or none has ever been
  evaluated; else 1-4, scaling with the fraction of governing contracts
  whose latest `Evaluation` passed — reusing `engines.evaluation
  .passed_evaluation_keys()` per contract subject rather than
  reimplementing "latest evaluation wins." Never 5.
- `chain.py::tasks_governed_by_delivery_capability()` — the reverse of
  `orchestrator/staffing.py::engineering_roles_for_obligation()`'s
  forward walk: `DeliveryCapability.realized_by_roles →
  EngineeringResponsibility.fulfilled_by_role_keys (reverse scan) →
  DeliveryRole.responsibility_keys (reverse scan) →
  DeliveryRole.accountable_for_task_keys`.
- `analysis.py::analyze_capability_gaps()` — diffs each already-computed
  `Capability`/`DeliveryCapability.maturity` against a caller-supplied
  `desired_maturity: dict[str, int]`, building a `CapabilityGap` when
  current < desired. `recommended_role_keys`: a reverse scan of
  `registry.engineering_roles` for `required_capabilities` (technical),
  or `registry.delivery_capabilities[key].realized_by_roles` directly
  (delivery — already-curated, no scan needed). `provenance=OBSERVED`
  (a deterministic diff of two known numbers is transcription, not
  inference — unlike the maturity scores themselves, which the
  orchestrator layer marks `INFERRED`). `priority` scales with
  `gap_size` via a stated rule: `>=3 → 1`, `==2 → 2`, else `3`.

**`orchestrator/gap_analysis.py`, the I/O layer.** `GapAnalysisRequest
(desired_maturity)` in; `GapAnalysisOutcome(gaps, recommendations)` out.
`analyze_project_capability_gaps()` fetches real project facts
(`Pipeline`, `Test`, `Evaluation`) by filtering `MetadataRepository
.list()` — mirroring `orchestrator/gate.py`'s own `_stored_evaluations()`/
`_requirement_refs_for_project()` idiom exactly, **not**
`webui/graph_discovery.py`'s graph-traversal idiom, because nothing this
step needs requires a traversal: `Pipeline`/`Test` carry `project_ref`
directly, and `Evaluation.subject_ref` is filtered per governing
contract, not per project. Consequently **`run_cycle()`'s signature did
not need a new `graph: GraphRepository` parameter** — a real
simplification found during implementation, not assumed going in; the
step takes only the `metadata: MetadataRepository` every step already
receives. Inferred `Capability`/`DeliveryCapability` instances get
deterministic ids (`f"{project_ref.id}:{capability_key}"`) so repeated
runs upsert in place rather than duplicate. Each `CapabilityGap` is
persisted plus a `HAS_GAP(Project, CapabilityGap)` edge (a real
relationship type, `source_types: [Project]`, `target_types:
[CapabilityGap]`). For each gap's `recommended_role_keys`,
`GapStaffingRecommendation` wraps the existing, untouched `resolve_role()`
— no contract, since a capability gap is not task-scoped — and is
**never written as `IMPLEMENTED_BY`**: advisory only.

**`run_cycle()` gains `gap_analysis: GapAnalysisRequest | None = None`**,
keyword-only, purely additive — every existing call site is unaffected.
When supplied, it runs early, independent of `change`/`observe`: a
standing capability-maturity assessment, not something a change triggers.
`CycleReport` gains `gap_analysis: GapAnalysisOutcome | None = None`.
Failures go through the existing `_record()`/`on_error="collect"`
discipline, unchanged.

## Consequences

**Good.** The metamodel's own capability catalogs finally have a
consumer: `detection_hints` and `realized_by_roles`, loaded since Phase
1 and unused since, now drive a real, itemized, per-project gap report.
The honesty discipline `docs/orchestrator.md` already established for
`GateState` extends cleanly here — maturity is `INFERRED` with a stated
confidence, never dressed up as certified, and the gap diff itself stays
`OBSERVED` because it really is just arithmetic on two known numbers.

**Costs, stated honestly.** Maturity inference is coarse by design — a
project with excellent transformation logic but zero recorded `Test
.covers_refs` scores the same low technical maturity as one with none at
all, because test-coverage evidence is the only signal this phase counts.
Populating `covers_refs`/richer registry `detection_hints` would sharpen
the signal; out of scope here. Delivery maturity is entirely dependent on
`Evaluation`s already existing against the right `DeliveryContract`
subject — a project that has never run an evaluation scores 0 regardless
of how mature its actual process is, an honest floor, not a defect.

**Risk accepted.** `GapStaffingRecommendation`'s `resolve_role()` call has
no contract, so it never demotes a role-satisfying-but-non-conformant
agent (ADR-0020's own mechanism) — a gap recommendation can name an agent
that would, if actually staffed against a real task, fail delivery
conformance. Acceptable because the recommendation is advisory, not a
staffing write; ADR-0020's conformance check still gates the moment that
role is actually staffed against a real task obligation via
`orchestrator/staffing.py`.

## Alternatives rejected

**Reusing `ProjectGraphService.assess_readiness()`/`GateReadiness.status`
as the delivery-capability maturity signal.** Rejected — it would
silently inherit the documented "4 of 6 `GateState` dimensions have no
real assembler" gap, reporting maturity for controls nothing actually
assembled.

**Automatically writing `IMPLEMENTED_BY` from a gap's recommended
role.** Rejected — conflates an advisory "this role would help" signal
with the binding "this agent implements this role for this task"
semantics `IMPLEMENTED_BY` already carries from ADR-0016; a capability
gap is not a `DeliveryObligation` and shouldn't be treated like one.

**A fifth, automatically-inferred maturity level ("optimizing").**
Rejected — level 5 requires trend/history data (is this capability
*improving*, sustained over time) this platform does not track. Capping
inference at 4 is honest about what a single snapshot can support;
adding level 5 would require either fabricating a signal or persisting
run-over-run history, both out of scope.

**Adding a new `graph: GraphRepository` parameter to `run_cycle()`,**
considered going in (to mirror `webui/graph_discovery.py`'s traversal
idiom). Rejected once `orchestrator/gate.py`'s own precedent was checked
directly: every fact this step needs is reachable by filtering
`MetadataRepository.list()`, exactly as `gate.py` already does for
`Evaluation`/`Requirement` — no traversal, no new required parameter, no
call-site churn.
