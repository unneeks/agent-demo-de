# ADR-0020: Composition calls `DeliveryContract.conformance_of()` for real

**Status:** Accepted · **Date:** 2026-08-10 · **Phase:** —

## Context

The original spec described the Composition Engine as: "Given a
project's capability gaps, resolves which Engineering Roles are needed,
selects Agents from the marketplace, and checks delivery conformance
(§15) — the piece that calls `DeliveryContract.conformance_of()` for
real." Auditing the built code against that line surfaced a real,
self-acknowledged gap: `engines/composition/resolution.py`'s own
docstring stated composition is "distinct from, and complementary to"
`conformance_of()` and deliberately never called it — a documented Phase
4 decision (ADR-0014), not an oversight. But `domain/metamodel/entities/
delivery/contracts.py`'s own module docstring says `conformance_of()`
"answers the question the composition engine must ask and the original
design could not... That is the difference between a copilot and a
member of a digital engineering organization." The two documents
disagreed with each other, and the original spec's claim about
composition was, verified directly, false.

Verified before designing anything: `DeliveryContract.conformance_of()`
is fully built and tested — nothing to add there. `LoadedDeliveryModel.
contract_for(task_key)` already auto-derives a real `DeliveryContract`
for every task with `mandatory_control_refs` (9 of the worked model's 13
tasks). Two real catalog agents (`regression-agent`, `data-model-composer`)
already declare `Agent.delivery.supported_checklist_keys`/
`supported_gate_keys`/`supported_artifact_kinds` matching their tasks'
real contracts exactly — a positive worked example already exists in
committed registry data, confirmed by calling `resolve_role(..., contract=
delivery_model.contract_for("task.regression-test"))` directly before
relying on it. Nothing in `engines/composition/` or `orchestrator/
staffing.py` had ever called `contract_for()` or `conformance_of()`.

**Scope, per explicit user decision:** wire `conformance_of()` only. The
other half of the spec line — "given a project's capability gaps,
resolves which roles are needed" — requires a gap-analysis engine that
does not exist at all: no code anywhere constructs a `Capability`/
`DeliveryCapability`/`CapabilityGap` instance, and the registry has no
"desired maturity" data to compare against. Explicitly deferred, not
part of this change.

## Decision

**`resolve_role()` gains an optional, default-`None` `contract:
DeliveryContract | None` parameter.** When supplied, every candidate is
also assessed via a new `assess_conformance()` — a thin wrapper over
`contract.conformance_of()`, mirroring `assess_candidate()`'s own
existing discipline of never recomputing what a lower-level primitive
already computes. `CandidateAssessment` gains an additive `conformance:
ContractConformance | None = None` field. `RoleResolution`'s two-bucket
shape (`matches`/`near_misses`) is unchanged; a candidate now counts as a
real match only when it satisfies the role **and** (no contract was
given, or it is conformant to the one that was) — demoting a
role-satisfying-but-non-conformant candidate to `near_misses`, its
itemized `ContractConformance.blocking_gaps` attached for visibility.

**`orchestrator/staffing.py::select_agents()`** resolves
`delivery_model.contract_for(obligation.key)` for `"task"` obligations
(the only kind whose key is a `DeliveryTask` key) and passes it through
to `resolve_role()`. `"approval"` obligations' keys are `DeliveryRole`
keys, not task keys, so they keep today's role-only behaviour exactly.
`StaffingOutcome` needed no new field — `resolution: RoleResolution |
None` was already one, so `outcome.resolution.best_match.conformance` is
already reachable.

**`resolve_catalog()` stays untouched, deliberately.** It resolves every
role against the whole catalog with no project or task in view — there
is no contract to check. The split the codebase already documented
("catalog-wide" vs. "project-and-task-specific") stays real, not
notional: only project-scoped staffing gained conformance-awareness.

## Consequences

**Good.** `contracts.py`'s own stated purpose — "can this agent do the
work according to the organization's delivery model" gating real
staffing — is finally true, not aspirational. The worked
`task.regression-test` → `regression-agent` staffing decision is now
provably conformant, not just role-matched, verified directly:
`resolve_role(regression_engineer_role, catalog, contract=contract_for
("task.regression-test"))` returns `regression-agent` in `matches` with
`conformance.is_eligible=True`, and demotes `copilot-coding-agent-regression`
to `near_misses` with `conformance.is_eligible=False` — the same, real
registry data, now correctly discriminated.

**Costs, stated honestly.** `Agent.delivery` declarations
(`supported_checklist_keys`/`supported_gate_keys`/`supported_artifact_kinds`)
are sparse across the real catalog — only 2 of 6 agents declare any.
Several roles that previously showed one clean role-satisfying match will
now show zero conformant matches for their contract-bearing tasks, once a
caller supplies a real contract — an honest finding this change surfaces
for the first time, not a regression this change causes. Fixing that
requires populating more agents' `delivery` declarations, a registry-data
change outside this ADR's scope.

## Alternatives rejected

**A third `RoleResolution` bucket** (e.g.
`role_satisfied_but_non_conformant`) instead of demoting into
`near_misses`. Rejected — adds an API surface no current caller needs;
`near_misses` plus the attached `ContractConformance.blocking_gaps`
already carries the same information, and every existing consumer of
`RoleResolution`'s two-bucket shape keeps working unmodified.

**Folding conformance into `CandidateAssessment.satisfies` directly**
(making `satisfies` mean "role-satisfied and, if applicable,
conformant"). Rejected — `satisfies` is an existing, tested field whose
meaning ("covers everything `EngineeringRole` needs") several callers
(including `resolve_catalog()`, which never has a contract) already rely
on; silently redefining it would be a breaking change dressed up as a
bug fix.

**Making `contract` required** (forcing every `resolve_role()` caller to
either supply one or explicitly pass `None`). Rejected — `resolve_catalog()`
and every existing test call `resolve_role()` with no notion of a
project or task; an optional, default-`None` parameter is what makes this
purely additive.
