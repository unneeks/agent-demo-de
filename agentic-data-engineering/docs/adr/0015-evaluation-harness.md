# ADR-0015: An evaluation harness that runs suites and gates the agent lifecycle, reusing existing scoring primitives

**Status:** Accepted · **Date:** 2026-08-09 · **Phase:** 5

## Context

`Evaluation`/`EvaluationSuite`/`EvaluationMetric`/`EvaluationScenario`/
`MetricResult` (`domain/metamodel/entities/evaluation/evaluation.py`) have
been modeled since Phase 1, with real pure functions already attached —
`Evaluation.trust_score` (`= min(score, delivery_score)`),
`Evaluation.weighted_score()`, `EvaluationMetric.passes()` — but nothing has
ever called them together to run a suite and produce an `Evaluation`. The
package's own `__init__.py` docstring already named this: "Phase 1 models
evaluation; it does not run it."

Two concrete gaps made this actionable rather than aspirational:

1. **A real dangling reference already sits in the reviewed worked delivery
   model.** `gate.architecture-review` (`delivery-models/
   data-engineering.yaml:606-616`, blocking, risk `HIGH`) declares
   `required_evaluations: [architecture-quality-evaluation]` — a suite key
   never defined anywhere, and never checked either.
2. **`GateState.passed_evaluations`'s own docstring expects a caller-provided
   assembler** ("Assembled by the caller from the graph") that nothing in the
   codebase provides; every existing test constructs it by hand. Separately,
   `Agent.transition_to()` is purely structural — the lifecycle's own naming
   (`EVALUATED`, `CERTIFIED`) implies evaluation gates promotion, but no code
   path anywhere conditions a transition on an actual `Evaluation` result.

## Decision

**Three new registry catalogs** (`evaluation_metrics.yaml`,
`evaluation_scenarios.yaml`, `evaluation_suites.yaml`), separate flat files
rather than one bundle, because `EvaluationMetric`/`EvaluationScenario` are
reusable entities referenced by key from multiple suites — the same
reference-not-inline shape `Agent.skills`/`Agent.tools` already use — not
1:1-owned children the way a `ChecklistItem` is owned by exactly one
`Checklist` in the bundled delivery-model file.

**Two worked suites.** `architecture-quality-evaluation` (`level: workflow`)
closes the real dangling reference: its `applies_to` names
`task.solution-architecture`, whose deliverable it genuinely evaluates —
`level: agent` was rejected because `gate.architecture-review`'s
`required_roles: [solution-architect]` names a `DeliveryRole` with no
corresponding `EngineeringRole`/`Agent` in the catalog. Its 4 metrics map
one-to-one onto `architecture-checklist`'s real items (`ARC-01`–`ARC-04`).
`regression-agent-certification` (`level: agent`) is built directly from
`regression-engineer`'s own `evaluation_criteria` and
`minimum_evaluation_score`/`minimum_delivery_conformance` — not arbitrary
numbers.

**A new engine, `engines/evaluation/`, reusing `EvaluationMetric.passes()`/
`Evaluation.weighted_score()` rather than reimplementing scoring.**
`run_suite()` is pure arithmetic over caller-supplied `observed_values`.
`passed_evaluation_keys()` provides the assembler `GateState`'s docstring
always expected — latest evaluation per suite key wins, not "any passing
ever," so a stale pass can't paper over a later failure and a stale failure
can't keep blocking a gate after a later pass. `advance_agent()` wraps
`Agent.transition_to()` — gating exactly `-> EVALUATED` and `-> CERTIFIED`,
leaving every other legal transition (retreats, retirement, deployment,
re-evaluation flagging) ungated, and leaving the underlying structural
legality table untouched and still authoritative underneath.

## Consequences

**Good.** `GateState.passed_evaluations` finally has a real assembler
instead of an unfulfilled docstring promise. The dangling
`gate.architecture-review` reference is closed with real, referentially
checked data — `MetamodelRegistry.validate()` now catches a future
occurrence of the same mistake instead of silently accepting it.
`Deployment.evaluation_ref` can now cite something genuinely constructible
end to end (`Deployment` itself untouched — it already correctly enforces
only citation, not validity, the same discipline `Finding.evidence_refs`
already uses).

**Costs, stated honestly.** `engines/gates/readiness.py`'s evaluations
dimension still cannot distinguish "never evaluated" from "evaluated and
failed" — both collapse to the same `BlockingItem(detail="required
evaluation has not passed")`. This is a deliberate, named non-fix: fixing it
would mean changing `GateState`'s shape or `readiness.py`'s logic, and this
phase was scoped to *providing the assembler `readiness.py` already
expected*, not modifying `readiness.py` itself. `advance_agent()` does not
cross-check the cited `Evaluation`'s suite `level` against the transition
being gated — an `EVALUATED` transition backed by a `skill`-level suite's
passing `Evaluation` would be accepted, because `Evaluation` carries a
`suite_ref` but no denormalized `level`, and adding a registry lookup would
break the plain-domain-objects purity this engine otherwise shares with
`engines/composition`. Only 2 suites are populated; every other engineering
role's certification and every other gate's evaluation need remain
unmodeled. No scheduled/automatic evaluation runs exist.

## Alternatives rejected

**Bundling the evaluation catalog into one file, like a delivery model.**
Rejected: metrics and scenarios are reusable, independently addressable
entities referenced by key from multiple suites, not children owned 1:1 by
one parent — the coupling shape delivery-model bundling assumes doesn't
apply here.

**`run_suite()` taking the whole `MetamodelRegistry` instead of a plain
`metrics` dict.** Rejected: mirrors `resolve_role()`/`resolve_catalog()`'s
split in `engines/composition` — keeps the scoring core testable and
registry-free; no caller needs a registry-aware wrapper yet, so none is
built ahead of need.

**Fixing `readiness.py`'s missing-vs-failed ambiguity now.** Rejected as out
of scope for this phase; recorded as a named cost above rather than silently
left unaddressed.

**Cross-checking `EvaluationSuite.level` inside `advance_agent()`.** Rejected
for the same reason `run_suite()` doesn't take a registry — it would require
`advance_agent()` to look up the suite by key rather than operate purely on
the `Evaluation` object handed to it, breaking the plain-domain-objects
contract every other function in `engines/evaluation`/`engines/composition`
shares.
