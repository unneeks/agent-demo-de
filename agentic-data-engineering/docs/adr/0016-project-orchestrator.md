# ADR-0016: A project orchestrator that composes existing engines and closes their deferred write path

**Status:** Accepted · **Date:** 2026-08-09 · **Phase:** 6

## Context

Phases 1–5 built five independent pieces of the continuous loop
`docs/architecture.md` diagrams — impact analysis, checklist evaluation and
gate readiness (Phase 1), discovery (Phase 3), marketplace composition
(Phase 4), evaluation (Phase 5) — but nothing had ever called them together
over one real project. Two concrete gaps made this actionable:

1. **No write path exists from composition or evaluation results back into
   the graph.** Both engines' own docs named this as deferred, in their own
   words: `docs/marketplace.md`: "Persisting a specific project's staffing
   decision (an `IMPLEMENTED_BY` edge scoped to one project) is **future
   orchestrator work**." `docs/evaluation.md`: "No write path... matching
   `engines/composition`'s boundary."
2. **`engines.impact.traceability.traceability_score()` is real, correct,
   and completely unwired.** Its own docstring says "this is what feeds
   `GateState.traceability`," but nothing anywhere called it and wired the
   result into a real `GateState` — confirmed by grepping every `GateState(`
   construction site in the repo (only test files, all hand-fed literal
   values).

`GateState`'s field-by-field assembler status, verified before designing
anything: `passed_evaluations` had a real assembler (Phase 5's
`passed_evaluation_keys()`); `traceability` had a real, unwired one;
`present_artifact_kinds`, `checklist_outcomes`, `satisfied_evidence`,
`approvals` had none — every test hand-writes literal sets, with zero code
path from real project graph state to any of the three (a fourth,
`checklist_outcomes`, has a real *reduction* but its input stays
caller-supplied).

## Decision

**A new package, `orchestrator/`, with `run_cycle()`** composing OBSERVE
(optional, calls the existing `discover_project`) → DETECT CHANGE + IMPACT
(calls `service.analyze_change`) → SELECT AGENTS (walks the real four-level
role chain, calls `resolve_role`, writes `IMPLEMENTED_BY`) → EVALUATE (calls
`run_suite`/`advance_agent`, writes the `Evaluation` + `EVALUATES` + the
advanced `Agent`'s status) → APPROVAL GATE (assembles `GateState` with two
real, graph-sourced fields plus four explicitly caller-supplied ones, calls
`service.assess_readiness`).

**Wherever the query facade already covers a step, the orchestrator calls
it, never the raw `engines.*` function** — per ADR-0011's whole reason to
exist. `ProjectGraphService` gains a fourth facade method,
`assess_traceability()`, applying a precise test: a function gets a facade
method iff it takes a `GraphRepository` (`analyze_impact`, `trace`,
`traceability_score` all do). `run_suite`/`resolve_role` do not, and are
deliberately **not** wrapped — both modules' own docstrings state "no
`ProjectGraphService`" as their design boundary; wrapping them would
contradict what Phases 4/5 explicitly wrote down.

**`IMPLEMENTED_BY` is written as a global catalog fact, not scoped
per-project.** `relationship_types.yaml` models it as `EngineeringRole ->
Agent` with no `Project` in either `source_types`/`target_types`, described
catalog-level ("An engineering role is implemented by an agent. The role
outlives the agent"). `Relationship.key` is `(source, type, target)` only,
so two projects staffing the same `(role, agent)` pair produce one shared
edge. This phase does not invent per-project cardinality the schema doesn't
support — that would be an unreviewed metamodel change, not an orchestrator
change. It writes `attributes={"project_id", "obligation_kind",
"obligation_key"}` as informational provenance, and the project-specific
staffing record lives in `CycleReport.staffing`.

**One small, verified-necessary metamodel fix**: `EVALUATES.target_types`
was missing `DeliveryArtifact` — confirmed by direct read
(`[Agent, Skill, Workflow, Project, DeliveryContract]`). Without it, running
Phase 5's own `architecture-quality-evaluation` worked example (which
evaluates a `DeliveryArtifact` subject, not an `Agent`) through the write
path this phase adds fails registry validation immediately. Fixed by adding
one target type — the smallest correct fix, not a silent workaround.
`IMPLEMENTED_BY` itself needed no fix; confirmed already legal exactly as
`EngineeringRole -> Agent`.

## Consequences

**Good.** `GateState.passed_evaluations` and `traceability` now have real,
tested assemblers sourced from actual persisted graph/metadata state — the
`gate.architecture-review` worked example goes `BLOCKED -> PASS` through
`run_cycle()` exactly as it did through Phase 5's hand-wired `GateState`.
Composition and evaluation's staffing/evaluation results are finally
queryable facts in the graph, not just returned Python objects a caller has
to remember to do something with.

**Costs, stated honestly.** Four of `GateState`'s six fields
(`present_artifact_kinds`, `checklist_outcomes`, `satisfied_evidence`,
`approvals`) remain hand-supplied by design — inventing artifact/evidence/
approval/checklist-result detection is its own, much larger future phase,
not folded in here. `IMPLEMENTED_BY` is a global catalog fact, not a
per-project one — a genuine semantic gap if per-project staffing history
ever needs first-class graph representation; documented rather than
silently accepted. `Deployment.evaluation_ref`/`approval_ref` still aren't
checked for resolving to anything real — deploying remains untouched,
future-phase territory.

## Alternatives rejected

**Wrapping `run_suite`/`resolve_role` into `ProjectGraphService`.** Rejected:
contradicts both modules' own stated "no `ProjectGraphService`" boundary,
written down explicitly in Phases 4/5.

**Wiring `evaluate_checklist()`'s `ChecklistItemResult` input too**, since
it's technically as reachable as `passed_evaluation_keys()` was. Rejected —
grouped deliberately with the other three caller-supplied `GateState`
fields, to hold a crisp scope line rather than a fuzzy "some of the boundary
is now gone" one.

**Silently skipping the `EVALUATES` registry fix** and just not writing that
edge for non-`Agent` subjects. Rejected — a workaround, not the smallest
correct fix, and it would have silently broken Phase 5's own flagship worked
example the moment it ran through a real write path.

**Scoping `IMPLEMENTED_BY` per-project via a new relationship type or a
project-qualified compound key.** Rejected — the registry's own description
already reads it as a global catalog fact; inventing per-project cardinality
the schema doesn't support is an unreviewed metamodel change, and a
separately-reviewed decision if a genuinely per-project staffing fact turns
out to be needed later.
