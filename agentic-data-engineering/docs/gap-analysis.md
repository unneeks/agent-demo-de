# Capability Gap Analysis

ADR-0020 wired the `DeliveryContract.conformance_of()` half of the original
spec's Composition Engine line into real staffing, but explicitly deferred
the other half: "given a project's **capability gaps**, resolves which
Engineering Roles are needed." This closes that half. See
[ADR-0021](adr/0021-capability-gap-analysis.md) for the full reasoning and
the alternatives rejected.

Two capability catalogs have existed since Phase 1 —
`metamodel-registry/capabilities.yaml` (technical) and
`delivery_capabilities.yaml` (delivery) — loaded into
`MetamodelRegistry.capabilities`/`.delivery_capabilities` as `CapabilitySpec`
(`domain/metamodel/registry.py`). Their `detection_hints` and
`realized_by_roles` fields were loaded and never consumed anywhere — the
same "metamodel anticipated this, nothing built it" shape `conformance_of()`
and `contract_for()` were in before ADR-0020.

## The one idea that must not be compromised

**Maturity inference is a coarse, evidence-counting proxy, explicitly
labelled as such — never presented as a certified assessment.**
`engines/gap_analysis/inference.py`'s two functions count real signal —
matching `detection_hints` against already-ingested `Pipeline`/`Test`
fields for technical capabilities; real, passing `Evaluation`s against a
capability's governing `DeliveryContract`s for delivery capabilities — and
scale 1–4 by how much of it exists. **Neither function ever returns 5
("optimizing")**: that requires human judgment and trend data this
platform doesn't have.

The `orchestrator/gap_analysis.py` I/O layer marks every inferred
`Capability`/`DeliveryCapability` instance `provenance=INFERRED` with a
fixed confidence, honestly. The gap diff itself
(`engines/gap_analysis/analysis.py::analyze_capability_gaps()`) is
`provenance=OBSERVED` — comparing two already-known numbers is
transcription, not inference.

## A finding that shaped the design

`ProjectGraphService.assess_readiness()`/`GateReadiness.status` was
considered and rejected as the delivery-capability maturity signal. Its own
docstring says four of `GateState`'s six dimensions
(`present_artifact_kinds`, `checklist_outcomes`, `satisfied_evidence`,
`approvals`) "have no real assembler anywhere in this codebase" — a
deliberate, already-documented gap (`docs/orchestrator.md`'s "what this is
not"). Using full gate readiness here would have silently laundered that
gap into a new engine, reporting artificially healthy maturity for a
capability whose gate was never really assessed. Delivery-capability
maturity therefore uses only the one honestly-computable signal that ties
to a specific capability: real, persisted `Evaluation`s against the
capability's governing `DeliveryContract`s.

## The reverse chain

`orchestrator/staffing.py::engineering_roles_for_obligation()` walks
forward: `DeliveryRole → EngineeringResponsibility → EngineeringRole`.
Closing a delivery capability's gap needs the reverse — which
`DeliveryTask`s does staffing that role chain actually govern?
`engines/gap_analysis/chain.py::tasks_governed_by_delivery_capability()`:

```
DeliveryCapability.realized_by_roles (registry.delivery_capabilities[key])
  -> EngineeringResponsibility.fulfilled_by_role_keys (reverse scan)
    -> DeliveryRole.responsibility_keys (reverse scan)
      -> DeliveryRole.accountable_for_task_keys
```

Worked example, against the real registry: `regression-assurance`'s
`realized_by_roles` is `[regression-engineer]`; `regression-engineer`
fulfils `resp.regression-proof`; `test-lead` (and `data-engineer`, which
also names that responsibility) is accountable for it —
`test-lead.accountable_for_task_keys` includes `task.regression-test`,
which has a real, auto-derived `DeliveryContract`
(`LoadedDeliveryModel.contract_for()`). A real, passing `Evaluation`
against that contract is what raises `regression-assurance`'s inferred
maturity above zero.

## Recommended roles

Sourced differently per capability kind, both from data the registry
already curates:

- **Technical `Capability`**: a reverse scan of `registry.engineering_roles`
  for `role.required_capabilities` containing the gap's key —
  `EngineeringRole.required_capabilities` already names exactly this.
- **Delivery `DeliveryCapability`**: `registry.delivery_capabilities[key]
  .realized_by_roles` directly — already-curated registry data, no scan
  needed.

## Staffing recommendations are advisory only

`GapStaffingRecommendation` wraps the existing, untouched
`resolve_role()` (Phase 4) — no contract, since a capability gap is not
task-scoped and has no specific `DeliveryContract` to check conformance
against. **No `IMPLEMENTED_BY` edge is ever written from a gap
recommendation.** A capability gap is a standing assessment, not a
specific piece of triggered work the way a `DeliveryObligation` is;
recommending a role for a gap is not the same speech act as staffing one
for a task.

## Wiring into `run_cycle()`

`run_cycle()` gains an optional, keyword-only `gap_analysis:
GapAnalysisRequest | None = None` parameter (ADR-0021). When supplied, it
runs early and **independently of `change`/`observe`** — a standing
capability-maturity assessment, not something a change triggers. Failures
go through the existing `_record()`/`on_error="collect"` discipline every
other step already uses. This did **not** require adding a new `graph`
parameter to `run_cycle()`'s signature: `orchestrator/gate.py`'s own
`_stored_evaluations()`/`_requirement_refs_for_project()` idiom — filtering
`MetadataRepository.list()` by `project_ref`/`subject_ref` — already
reaches everything this step needs (`Pipeline`, `Test`, `Evaluation`), so
`orchestrator/gap_analysis.py` mirrors that idiom rather than
`webui/graph_discovery.py`'s traversal. Every existing `run_cycle()` call
site is unaffected.

`request.desired_maturity` stays caller-supplied, required, never a
literal — no canonical "desired maturity" exists anywhere in the registry,
the same reasoning ADR-0019 applied to `ContextPolicy`. A key not present
in `desired_maturity` is simply not assessed, not an error.

## Errors

| Error | Raised when |
|---|---|
| `pydantic.ValidationError` (a `ValueError`) | A caller-supplied `desired_maturity` value falls outside `CapabilityGap`'s own `0-5` bound; recorded as a `CycleFailure` (`kind="gap_analysis_failed"`) under `on_error="collect"`, re-raised immediately under `"fail_fast"` |
| `IngestionError` | A `Capability`/`DeliveryCapability`/`CapabilityGap` write, or the `HAS_GAP` relationship write, is rejected; same `on_error` handling |

## What this is not

- **No discovery of capabilities not already in the registry catalog.**
  This step infers maturity for capabilities `capabilities.yaml`/
  `delivery_capabilities.yaml` already name; a `desired_maturity` key
  matching neither catalog is silently skipped, never a new
  `CapabilitySpec`.
- **5 ("optimizing") is never automatically inferred**, for either
  technical or delivery capabilities.
- **`desired_maturity` is never defaulted.** No canonical value exists
  anywhere in the registry to default it to.
- **No automatic `IMPLEMENTED_BY` write from a gap recommendation.**
  Recommendations are advisory (`GapAnalysisOutcome.recommendations`),
  never persisted as a staffing decision.
- **No UI or API surface this phase.** `webui/api/routes/cycles.py`'s
  `POST /api/cycles` does not accept a `gap_analysis` field; reachable
  only by calling `run_cycle(..., gap_analysis=...)` directly.
- **No trend/history tracking.** Each run computes maturity fresh from
  currently-persisted facts; nothing here compares this run's inferred
  maturity against a previous run's.
