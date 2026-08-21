# Evaluation Harness

`Evaluation`, `EvaluationSuite`, `EvaluationMetric`, `EvaluationScenario` and
`MetricResult` (`domain/metamodel/entities/evaluation/evaluation.py`) have
been modeled since Phase 1 — `Evaluation.trust_score` (`= min(score,
delivery_score)`) and `Evaluation.weighted_score()` are already real, tested
pure functions, and `EvaluationMetric.passes()` already decides pass/fail for
one observed value. But nothing has ever run a suite and produced an
`Evaluation` — the same gap `Agent`/`Skill`/`Tool` had before Phase 4, on the
same dormant-since-Phase-1 vocabulary the package's own docstring already
named: *"Phase 1 models evaluation; it does not run it. What exists here is
the vocabulary the harness will populate."*

Phase 5 is that harness: a populated evaluation catalog and a pure
`engines/evaluation/` engine that scores a suite from caller-supplied
observed values and reduces evaluation history into what `GateState` and
`Agent` lifecycle transitions need. See
[ADR-0015](adr/0015-evaluation-harness.md) for the full reasoning and the
alternatives rejected.

## The one idea that must not be compromised

**`run_suite()` is pure arithmetic over caller-supplied `observed_values`,
reusing `EvaluationMetric.passes()`/`Evaluation.weighted_score()` as ground
truth — it does not reimplement scoring.** Same discipline Phase 4's
`engines/composition` used reusing `EngineeringRole.is_satisfied_by()`.
Nothing in this phase measures anything itself; `EvaluationScenario` is
catalog data describing what *should* be measured, never something executed.

**`Agent.transition_to()` stays untouched.** `advance_agent()` wraps it —
checks a passing, subject-matching `Evaluation` exists for gated targets,
then calls the real method — matching how ADR-0011 kept `ProjectGraphService`
a thin wrapper rather than pushing policy into entities.

## The catalog

Three new registries, deliberately three separate flat files rather than one
bundle: `EvaluationMetric`/`EvaluationScenario` are reusable, independently
addressable entities referenced by key from multiple suites
(`EvaluationSuite.metric_refs`/`scenario_refs` are `list[EntityRef]`, the
same reference-not-inline shape `Agent.skills`/`Agent.tools` already use) —
not 1:1-owned children the way a `ChecklistItem` is owned by exactly one
`Checklist` in the bundled `delivery-models/data-engineering.yaml`.

| File | Entries |
|---|---|
| `metamodel-registry/evaluation_metrics.yaml` | 8 |
| `metamodel-registry/evaluation_scenarios.yaml` | 6 |
| `metamodel-registry/evaluation_suites.yaml` | 2 |

**`architecture-quality-evaluation` closes a real dangling reference.**
`gate.architecture-review` (`delivery-models/data-engineering.yaml:606-616`,
blocking, risk `HIGH`) has declared `required_evaluations:
[architecture-quality-evaluation]` since Phase 1, with nothing behind the key
and nothing validating it resolved:

```
Before Phase 5: RegistryError never fires -- nothing checks
                gate.required_evaluation_refs at all.
After Phase 5:  MetamodelRegistry.validate() checks every
                gate.required_evaluation_refs entry against
                registry.evaluation_suites, and it now resolves.
```

`level: workflow`, not `agent`: `gate.architecture-review`'s `required_roles:
[solution-architect]` names a `DeliveryRole` with no corresponding
`EngineeringRole`/`Agent` in the marketplace catalog — there is no candidate
agent this suite could certify. What it genuinely evaluates is
`task.solution-architecture`'s produced artifact, exactly what `workflow`
means among the four levels `EvaluationSuite.level` supports. Its 4 metrics
map one-to-one onto `architecture-checklist`'s real items (`ARC-01`–`ARC-04`)
— `nfr-coverage`/`integration-points-identified` blocking, matching
`ARC-01`/`ARC-02`'s mandatory+blocking status exactly; `vendor-neutral-
justification`/`cost-estimate-completeness` non-blocking, a deliberate,
separate judgment call at the metric level (a checklist item is a reviewer's
confirmation, a metric is a machine-scoreable proxy — they don't have to
agree on blocking status).

**`regression-agent-certification`** is `level: agent`, built directly from
`regression-engineer`'s own `evaluation_criteria` and thresholds
(`engineering_roles.yaml`) — `passing_score`/`passing_delivery_score` are set
exactly equal to that role's `minimum_evaluation_score`/
`minimum_delivery_conformance`, not arbitrary numbers.

## The evaluation engine

`engines/evaluation/harness.py`:

```python
def run_suite(
    suite: EvaluationSuite, metrics: dict[str, EvaluationMetric],
    subject_ref: EntityRef, observed_values: dict[str, float],
    *, evidence_refs=None, component_versions=None, evaluated_at=None,
) -> Evaluation: ...

def passed_evaluation_keys(
    evaluations: Iterable[Evaluation], *, subject_ref: EntityRef | None = None
) -> set[str]: ...
```

For each metric a suite requires, `run_suite()` looks it up in `metrics` and
its observed value in `observed_values` — raising `ValueError` for either
gap, since a suite that cannot be scored must fail loudly, not silently
under-score. It builds one `MetricResult` per metric via `metric.passes(value)`,
computes `score`/`delivery_score` via `Evaluation.weighted_score()`, and sets
`passed` so the constructed `Evaluation` can never trip its own
`_blocking_failure_fails_the_run` validator.

A suite with no delivery-dimension metric treats `delivery_score` as
trivially `1.0`, not `0.0` — the same "requires nothing is trivially
satisfied" idiom `engines/gates/readiness.py`'s `_score()` and
`engines/composition`'s `_coverage()` both already use. Falling through to
`weighted_score()`'s literal empty-list `0.0` here would make `trust_score =
min(score, delivery_score)` collapse to zero for every purely-technical
suite, which is not what an empty dimension means.

`passed_evaluation_keys()` reduces evaluation history the way
`GateState`'s own docstring expects a caller to ("assembled by the caller
from the graph") — nothing in the codebase did that before this phase. It
picks the **latest evaluation per suite key**, not "any passing ever": a
single lucky pass long ago must not paper over every run since, and a stale
failure must not keep blocking a gate after a later run passed.

## Gating the agent lifecycle

`engines/evaluation/lifecycle.py`'s `advance_agent()` wraps
`Agent.transition_to()`, requiring a passing, subject-matching `Evaluation`
only for `-> EVALUATED` and `-> CERTIFIED` (from any legal origin:
`CANDIDATE`/`REEVALUATION_REQUIRED -> EVALUATED`, `EVALUATED -> CERTIFIED`).
Every other legal transition needs none — an evaluation proves fitness, it
isn't required to retreat, retire, deploy (`Deployment`'s own citation check
is a different, untouched layer), or flag for re-evaluation, which would be
circular.

```python
agent = registry.agents["regression-agent"]           # status: CANDIDATE
evaluation = run_suite(
    registry.evaluation_suites["regression-agent-certification"],
    registry.evaluation_metrics,
    subject_ref=EntityRef(type=EntityType.AGENT, id="regression-agent"),
    observed_values={...},                              # passing
)
advance_agent(agent, AgentLifecycle.EVALUATED, evaluation=evaluation)
# agent.status is now EVALUATED
advance_agent(agent, AgentLifecycle.CERTIFIED, evaluation=evaluation)
# agent.status is now CERTIFIED
```

An evaluation for the wrong subject, or a failing one, is rejected before
`transition_to()` is ever called — a rejected precondition never leaves the
agent partially transitioned. The underlying structural legality table
(`AGENT_LIFECYCLE_TRANSITIONS`) still applies unmodified underneath: an
illegal jump (e.g. `CANDIDATE -> CERTIFIED`, skipping `EVALUATED`) still
raises even with a perfectly valid evaluation in hand.

## Closing the architecture-review gate

`gate.architecture-review`'s evaluations dimension, before and after a real
`Evaluation` exists:

```
No evaluation run:
  GateState(passed_evaluations=set())
  -> assess_gate(...) -> BLOCKED
     blocking item: architecture-quality-evaluation
       "required evaluation has not passed"

A real, passing run:
  evaluation = run_suite(suite, metrics, artifact_ref, observed_values)
  passed = passed_evaluation_keys([evaluation])   # {"architecture-quality-evaluation"}
  GateState(passed_evaluations=passed)
  -> assess_gate(...) -> evaluations dimension score 1.0
```

`engines.gates.assess_gate()` itself is completely unmodified — this is
proof that no change to `readiness.py` was needed, only a real assembler for
one of `GateState`'s fields.

## Errors

| Error | Raised when |
|---|---|
| `RegistryError`: unknown scenario / metric | A suite's `scenario_refs`/`metric_refs` names a key not in its catalog |
| `RegistryError`: unknown metric (scenario) | A scenario's `metric_keys` names a key not in `evaluation_metrics` |
| `RegistryError`: unknown evaluation suite | A gate's `required_evaluations` names a suite key that doesn't exist — the check that closes the dangling reference |
| `ValueError` (`run_suite`) | A suite references a metric not in the `metrics` dict passed in, or `observed_values` is missing an entry the suite requires |
| `ValueError` (`advance_agent`) | No evaluation supplied for a gated target; the evaluation's `subject_ref` doesn't name this agent; the evaluation didn't pass |
| `ValueError` (`Agent.transition_to`, unmodified) | The target isn't a legal transition from the agent's current status, regardless of any evaluation |

## What this is not

- **No agent runtime, no LLM calls, from this module** — `run_suite()` takes
  `observed_values` as a plain caller-supplied argument; nothing here
  measures anything itself. Phase 7 (`docs/agent-runtime.md`) adds a
  separate, opt-in runtime that can produce `Evidence` a caller feeds into
  `observed_values` by hand — `run_suite()` itself is untouched and still
  never synthesizes a value.
- **No fix to `engines/gates/readiness.py`'s "never evaluated" vs. "evaluated
  and failed" ambiguity** — `GateState.passed_evaluations` is still a bare
  `set[str]`; a suite key absent because it was never run and one absent
  because its latest run failed both read as the same
  `BlockingItem(detail="required evaluation has not passed")`. A deliberate,
  named non-fix: this phase's job was to provide the assembler `readiness.py`
  already expected, not to change `readiness.py` itself.
- **No `Deployment` changes** — `Deployment._production_requires_certification`
  already requires a cited `evaluation_ref`; this phase makes it possible to
  produce a genuinely valid one to cite, not to add cross-entity validation
  to `Deployment` that the citation is actually valid.
- **No `DeliveryContract.conformance_of()` changes** — confirmed cleanly
  separate; it has no evaluation dimension and none is added.
- **No automatic or scheduled evaluation runs** — every `run_suite()` call is
  caller-initiated with caller-supplied data.
- **No write path** — `engines/evaluation/` never calls `ProjectGraphService`
  or any persistence port, matching `engines/composition`'s boundary.
- **No `EvaluationSuite.level` cross-check inside `advance_agent()`** —
  `Evaluation` carries a `suite_ref` but no denormalized `level`; adding a
  registry lookup would break the plain-domain-objects purity this engine
  otherwise shares with `engines/composition`/`engines/gates`.
- **Only 2 of potentially many suites are populated** — every other
  `EngineeringRole` and every other gate's evaluation needs remain
  unmodeled.
