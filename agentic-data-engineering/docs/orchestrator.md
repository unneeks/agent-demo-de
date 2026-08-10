# Project Orchestrator

Phases 1–5 built five independent, mostly-pure pieces of the continuous loop
`docs/architecture.md` diagrams:

```
OBSERVE → DETECT CHANGE → TECHNICAL IMPACT + DELIVERY IMPACT → UPDATE CONTRACTS
   ▲                                                                 │
   │                                                                 ▼
OBSERVE ← DELIVER ← APPROVAL GATE ← EVALUATE ← COLLECT EVIDENCE ← SELECT AGENTS
                                                              ← RUN CHECKLISTS
                                                              ← RUN TESTS
```

Impact analysis, checklist evaluation and gate readiness were real code since
Phase 1. Discovery (OBSERVE) landed in Phase 3, composition (SELECT AGENTS)
in Phase 4, evaluation (EVALUATE) in Phase 5 — but nothing had ever called
them together over one real project. Both `engines/composition` and
`engines/evaluation` explicitly deferred their own write path in their own
docs: "Persisting a specific project's staffing decision... is **future
orchestrator work**" (`docs/marketplace.md`); "No write path... matching
`engines/composition`'s boundary" (`docs/evaluation.md`). Phase 6 is that
work. See [ADR-0016](adr/0016-project-orchestrator.md) for the full
reasoning and the alternatives rejected.

## The one idea that must not be compromised

**`run_cycle()` composes; it invents nothing.** Every step calls an existing
Phase 1–5 function with real data — no new scoring, no new resolution logic,
no new gate math. The only genuinely new code is the write path
(`IMPLEMENTED_BY`, `Evaluation` + `EVALUATES`, the advanced `Agent`'s status)
and two `GateState` assemblers (`passed_evaluations`, `traceability`) that
were always documented as caller-supplied but never had a caller.

## The composed pipeline

```
run_cycle(service, registry, delivery_model, project_ref, metadata, ...)

  GAP ANALYSIS (optional)     analyze_project_capability_gaps()     ADR-0021
                              -- runs independently of change/observe
        │
        ▼
  OBSERVE (optional)         discover_project()                    Phase 3
        │
        ▼
  DETECT CHANGE + IMPACT     service.analyze_change()               Phase 1/2
        │
        ▼
  SELECT AGENTS              engineering_roles_for_obligation()     new
                              + resolve_role()                      Phase 4
                              writes IMPLEMENTED_BY                 new
        │
        ▼
  EVALUATE                   run_suite() / advance_agent()          Phase 5
                              writes Evaluation + EVALUATES,
                              persists the advanced Agent            new
        │
        ▼
  APPROVAL GATE               assemble_gate_state()                 new
                               + service.assess_readiness()          Phase 1/2
```

Every step is independently optional except `project_ref` itself — a cycle
can be gate-reassessment-only, staffing-only, or the full pipeline. Every
write goes through `ProjectGraphService`, never `persistence.ports`
directly, mirroring `discovery/orchestrate.py`'s discipline exactly.
`on_error="collect"` (default) records a per-step failure as a
`CycleFailure` and continues — one obligation's or evaluation's rejected
write shouldn't discard every other step's good work. `"fail_fast"`
re-raises immediately.

## Closing the write path

Before this phase, both `engines/composition` and `engines/evaluation`
stated their boundary plainly:

> "No write path — `engines/composition` never calls `ProjectGraphService`
> or any persistence port. Persisting a specific project's staffing decision
> (an `IMPLEMENTED_BY` edge scoped to one project) is **future orchestrator
> work**." (`docs/marketplace.md`)
>
> "No write path — `engines/evaluation/` never calls `ProjectGraphService`
> or any persistence port, matching `engines/composition`'s boundary."
> (`docs/evaluation.md`)

`orchestrator/staffing.py` and `orchestrator/evaluate.py` close exactly
those two gaps — and only those two:

- `select_agents()` resolves an obligation to a staffable `EngineeringRole`
  via `resolve_role()`, then writes the winning match as a real
  `IMPLEMENTED_BY(EngineeringRole, Agent)` edge via
  `service.ingest_relationship()`. For a `"task"` obligation, it also
  resolves `delivery_model.contract_for(obligation.key)` and passes that
  real `DeliveryContract` through to `resolve_role()`, which now also
  checks each candidate's delivery conformance
  (`DeliveryContract.conformance_of()`, ADR-0020) — a role-satisfying
  agent that cannot discharge the contract's mandatory controls is never
  staffed.
- `run_evaluations()` calls the untouched `run_suite()`/`advance_agent()`,
  then persists the resulting `Evaluation` (`service.ingest_entity()`), an
  `EVALUATES(Evaluation, subject)` edge, and — if requested — the advanced
  `Agent`'s new `status`.

**`IMPLEMENTED_BY` is written as a global catalog fact, not scoped
per-project — a deliberate judgment call, stated plainly.**
`relationship_types.yaml` models it as `EngineeringRole -> Agent` with no
`Project` in either `source_types`/`target_types`, described as "An
engineering role is implemented by an agent. The role outlives the agent" —
catalog-level, not project-scoped. `Relationship.key` is `(source, type,
target)` only, so two projects staffing the same `(role, agent)` pair
produce **one** shared edge, last write's `attributes` win. This phase does
not invent per-project cardinality the schema doesn't support; it writes
`attributes={"project_id", "obligation_kind", "obligation_key"}` as
informational provenance on that shared edge, and the project-specific
staffing record lives in `CycleReport.staffing`, not solely in the graph.

## Wiring `traceability_score()`

`engines.impact.traceability.traceability_score()`'s own docstring has
always said "this is what feeds `GateState.traceability`" — but nothing
anywhere called it and wired the result into a real `GateState`, confirmed
by grepping every `GateState(` construction site in the repo (all hand-fed
literal values). `ProjectGraphService` gains a fourth query-facade method:

```python
def assess_traceability(self, starts: list[EntityRef], **kwargs) -> float:
    return traceability_score(starts, self._graph, **kwargs)
```

`orchestrator/gate.py`'s `assemble_gate_state()` reconstructs every
`Requirement` in the metadata plane whose `project_ref` matches, and feeds
their refs through this method — real, graph-sourced traceability, not a
literal.

## Capability gap analysis (ADR-0021)

`run_cycle(..., gap_analysis=GapAnalysisRequest(desired_maturity=...))`
infers coarse `Capability`/`DeliveryCapability` maturity from real
project facts, diffs it against the caller-supplied desired maturity, and
persists itemized `CapabilityGap`s plus advisory (never
`IMPLEMENTED_BY`-writing) role recommendations. `orchestrator/
gap_analysis.py`'s fetch follows `orchestrator/gate.py`'s own
`metadata.list(...)`-and-filter idiom, not a graph traversal — so this
step needed no new `graph: GraphRepository` parameter on `run_cycle()`.
See [`docs/gap-analysis.md`](gap-analysis.md) for the full design,
including the honesty-gap finding that shaped its delivery-maturity
signal.

## The four-level staffing chain, worked

`select_agents()` walks the real, already-modeled chain from a
`DeliveryObligation` to a staffable `EngineeringRole`:

```
DeliveryObligation(kind in {"task","approval"})
  -> DeliveryRole.responsibility_keys
    -> EngineeringResponsibility.fulfilled_by_role_keys
      -> EngineeringRole -> resolve_role(role, registry.agents.values(),
                                          contract=delivery_model.contract_for(key))
```

(`contract` is only ever non-`None` for `"task"` obligations, whose key
is a real `DeliveryTask` key; `"approval"` obligations' keys are
`DeliveryRole` keys and always resolve `contract=None`, unchanged
role-only behaviour.)

Verified end to end against the real worked delivery model, including two
real negative cases that are first-class, reportable outcomes — never
exceptions, never silently dropped:

| Obligation | Delivery role | Responsibility | Engineering role | Agent |
|---|---|---|---|---|
| `task.regression-test` | `test-lead` | `resp.regression-proof` | `regression-engineer` | `regression-agent` |
| `task.logical-data-model` | `data-architect` | `resp.architecture-integrity` | `data-architect` | **none** — zero candidate agents |
| `task.logical-data-model` | `data-architect` | `resp.logical-data-design` | `data-model-engineer` | `data-model-composer` |
| `task.logical-data-model` | `data-architect` | `resp.architecture-signoff` | **none** — `fulfilled_by_role_keys: []` | n/a |

`resp.architecture-signoff`'s empty `fulfilled_by_role_keys` is real registry
data, not an edge case invented for this doc: "Accept, on the organization's
behalf, that a design is fit to build. This is an accountability, not a
task" — `delegable_to_agent: false`. No engineering role can ever fulfil it,
by design.

## Errors

| Error | Raised when |
|---|---|
| `OrchestratorError` | An `ObserveRequest.project.id` doesn't match `run_cycle`'s own `project_ref.id` |
| `UnknownGateError` | A `GateRequest.gate_key` names a gate the delivery model doesn't have |
| `IngestionError` (staffing) | Caught internally; recorded as `StaffingOutcome.implemented_by_written=False`, never raised past `select_agents` |
| `ValueError`/`IngestionError` (evaluate, gate) | Recorded as a `CycleFailure` under `on_error="collect"` (default); re-raised immediately under `"fail_fast"` |

## What this is not

- **No agent runtime, no live LLM calls, from these Phase 6 steps.**
  OBSERVE, DETECT CHANGE + IMPACT, SELECT AGENTS and APPROVAL GATE call
  `discover_project()` (itself unchanged, only calling an
  `ExtractionClient`), `run_suite()`, `resolve_role()`, `assess_gate()` — all
  pre-existing, none of them invoking a model. Phase 7 (`docs/agent-runtime.md`)
  adds a separate, new, opt-in RUN AGENT step
  (`agent_run_requests`, composed after SELECT AGENTS and before EVALUATE)
  that does invoke a real `AgentLLMClient` backend — every tool call it makes
  is still answered by `SimulatedToolExecutor`, never a real side effect.
- **No live measurement.** `EvaluationRequest.observed_values` stays a plain
  caller-supplied dict, exactly as `run_suite()` itself already requires.
- **No autonomous artifact/evidence/approval/checklist-result detection.**
  `present_artifact_kinds`, `checklist_outcomes`, `satisfied_evidence`,
  `approvals` all stay caller-supplied on `GateRequest`, named explicitly as
  a deliberate boundary — not silently ignored. `evaluate_checklist()`'s
  `ChecklistItemResult` input is technically as wireable as
  `passed_evaluation_keys()` was, and is deliberately **not** wired here to
  keep the boundary crisp rather than fuzzy. This same finding is why
  `docs/gap-analysis.md` (ADR-0021) does not reuse `assess_readiness()`/
  `GateReadiness.status` as its delivery-capability maturity signal.
- **No `Deployment`/DELIVER-step automation.** Deploying stays a separate,
  human/future-phase-triggered action; `Deployment.evaluation_ref`/
  `approval_ref` still aren't checked for resolving to anything real.
- **No scheduled/continuous/daemon execution.** `run_cycle()` is one call,
  one cycle, over one project, triggered by a caller. No polling, no loop
  that runs itself.
- **No API, no UI.** These are the only two layers `docs/architecture.md`'s
  layered diagram still marks `(later)` as of Phase 7.
