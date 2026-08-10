# Marketplace — Catalog and Role-Level Composition

Phases 1–3 built the metamodel, `ProjectGraphService`, and discovery — but one
piece of the metamodel has sat unused since Phase 1:
`EngineeringRole.is_satisfied_by()`/`missing_requirements()`
(`domain/metamodel/entities/organization/roles.py`) is the actual role/agent
matching logic, and until now nothing populated the catalog it needs to run
against. `Agent`, `Skill`, `Tool` and `KnowledgePack` were fully modeled
(`domain/metamodel/entities/organization/agents.py`) with no registry catalog,
unlike capabilities, roles and platforms, which already load from YAML.

Phase 4 is the marketplace: a populated catalog, a pure engine that resolves
roles against it, and the three GitHub Copilot integration points that
`docs/adr/README.md`'s "Deferred, and why" section had named but not started.
See [ADR-0014](adr/0014-marketplace-catalog-and-role-level-composition.md) for
the full reasoning and the alternatives rejected. A later change, extending
composition to actually call `DeliveryContract.conformance_of()` from real
project staffing, is covered by
[ADR-0020](adr/0020-composition-conformance.md).

## The one idea that must not be compromised

**Composition reuses existing role-satisfaction logic; it does not
reimplement it.** `engines/composition/resolution.py`'s `assess_candidate()`
is a thin wrapper calling `EngineeringRole.is_satisfied_by()`/
`missing_requirements()` with sets built from an `Agent`'s declared
`capabilities`/`delivery_capabilities`/`skills`/`tools`/`knowledge_packs`. The
engine's job is catalog-wide framing — partition into matches and
near-misses, rank, expose per-candidate gaps — not a second definition of
what "satisfies a role" means.

Role satisfaction answers a catalog-wide question: "which agents in the
whole marketplace satisfy this role, and how close do the rest come?" It
is a different question from `DeliveryContract.conformance_of()`
(`domain/metamodel/entities/delivery/contracts.py`), which answers a
narrower, project-and-task-specific one: "can this one agent execute this
one task under this organization's process?" — and composition still does
not reimplement that either. `assess_conformance()` is the same kind of
thin wrapper `assess_candidate()` already is, this time over
`conformance_of()`. What changed (ADR-0020): `resolve_role()` now accepts
an *optional* `contract` parameter, and `orchestrator/staffing.py`'s
SELECT AGENTS step supplies a real one — resolved via
`LoadedDeliveryModel.contract_for(task_key)` — for every task obligation.
A role-satisfying agent that cannot discharge that contract's mandatory
controls is demoted out of `matches`, never written as `IMPLEMENTED_BY`.
Leaving `contract=None` (the default, and every catalog-wide caller like
`resolve_catalog()`) preserves the original role-only behaviour exactly.

## The catalog

Four new registries under `metamodel-registry/`: `skills.yaml` (14 entries),
`tools.yaml` (7), `knowledge_packs.yaml` (5), `agents.yaml` (6). Built
exactly from the `required_skills`/`required_tools`/`required_knowledge`
keys already declared on the 5 engineering roles marked "staffed in the MVP"
in `engineering_roles.yaml` — `regression-engineer`,
`impact-analysis-engineer`, `data-quality-engineer`, `data-model-engineer`,
`delivery-compliance-engineer`. The 7 "catalogued, not staffed" roles'
skill/tool/knowledge keys are deliberately not covered (see "What this is
not" below).

Five of the six catalog agents each fully satisfy their role:
`regression-agent`, `impact-analysis-agent`, `data-quality-agent`,
`data-model-composer`, `delivery-compliance-agent`. The sixth,
`copilot-coding-agent-regression`, is deliberately incomplete — it is missing
the `impact-analysis` skill, the `regression-assurance` delivery capability,
and the `project-architecture` knowledge pack that `regression-engineer`
requires, so `missing_requirements()` has something real to report:

```python
>>> role = registry.engineering_roles["regression-engineer"]
>>> agent = registry.agents["copilot-coding-agent-regression"]
>>> role.missing_requirements(
...     capabilities=set(agent.capabilities),
...     delivery_capabilities=set(agent.delivery_capabilities),
...     skills=set(agent.skills),
...     tools=set(agent.tools),
...     knowledge=set(agent.knowledge_packs),
... )
{'capabilities': ['impact-analysis'],
 'delivery_capabilities': ['regression-assurance'],
 'skills': ['impact-analysis'],
 'tools': [],
 'knowledge': ['project-architecture']}
```

## The composition engine

`engines/composition/resolution.py` — pure, no I/O, no `ProjectGraphService`,
no persistence. It never touches a `GraphRepository`; it operates only over
static registry catalog data, which is what makes it the simplest of the four
engines (`engines/context/`, `engines/gates/`, `engines/impact/`,
`engines/composition/`).

```python
def assess_candidate(role: EngineeringRole, agent: Agent) -> CandidateAssessment: ...
def resolve_role(role, candidates, *, strict_role_match: bool = True) -> RoleResolution: ...
def resolve_catalog(registry: MetamodelRegistry) -> dict[str, RoleResolution]: ...
```

`resolve_role`'s `strict_role_match=True` default only considers agents whose
declared `role_key` matches the role being resolved — `IMPLEMENTED_BY`'s own
semantics: an agent is built to implement one specific role. Setting it
`False` widens the search to the whole candidate pool regardless of declared
role, for the different (also real) question "does anything already in the
catalog happen to cover this gap."

A worked `RoleResolution` for `regression-engineer`:

```
regression-engineer: 1 match, 1 near-miss
  matches:
    regression-agent            coverage 100%
  near_misses:
    copilot-coding-agent-regression  coverage  71%
      capabilities: impact-analysis
      delivery_capabilities: regression-assurance
      skills: impact-analysis
      knowledge: project-architecture
```

`CandidateAssessment.coverage` is a resolution-time heuristic — the fraction
of a role's required keys an agent already declares, with "requires nothing"
in a dimension treated as trivially fully covered (the same idiom
`engines/gates/readiness.py`'s dimension scoring uses). It is **not** a
certification score or a trust score; nothing about it depends on whether the
agent has ever been evaluated.

`scripts/validate_registries.py` prints a one-line-per-role marketplace
summary on every run, driven by `resolve_catalog()`.

## The three GitHub Copilot integration points

`docs/adr/README.md`'s "Deferred, and why" section named three integration
points. All three land here as **registry or schema data only** — no live
call, no runtime, no subprocess:

| Point | What lands | Where |
|---|---|---|
| Copilot code review as a marketplace `Tool` | `github` tool gains a `copilot_code_review` action, `LOW_RISK_WRITE`, findings framed as `Evidence(evidence_kind="review_record")` | `tools.yaml` |
| GitHub Models behind the configurable model provider | No schema change needed — `Agent.model_provider`/`model_name` were already free-form strings "the runtime resolves." `model_provider="github-models"` is a worked, proven-to-load catalog value | `agents.yaml`'s `data-quality-agent` |
| Copilot coding agent as an `EXTERNAL_AGENT` role implementation | New `ExecutionModel.EXTERNAL_AGENT` value + `Agent.external_provider` field/validator — the concrete "provider binding on `Agent`" ADR-0009 flagged as a known, accepted refactor | `enums.py`/`agents.py`; `agents.yaml`'s `copilot-coding-agent-regression` |

None of these executes anything. No HTTP call, no `gh`/`copilot` subprocess,
no GitHub API client — proven by unit tests that construct the data and
assert its shape, never a live call.

## Errors

| Error | Raised when |
|---|---|
| `RegistryError`: unknown engineering role | An agent's `role_key` names a role that doesn't exist |
| `RegistryError`: unknown capability / delivery capability | An agent declares a capability key not in `capabilities.yaml`/`delivery_capabilities.yaml` |
| `RegistryError`: unknown skill / tool / knowledge pack | An agent (or a skill's own `required_tools`/`required_knowledge`) references a catalog entry that doesn't exist |
| `RegistryError`: duplicate key | Two entries in the same catalog file share a key |
| `ValidationError`: `EXTERNAL_AGENT` but no `external_provider` | `Agent._external_agent_needs_a_provider` — the platform must know which external system executes the role's work in order to attribute and govern what it produces |

`MetamodelRegistry.validate()` reports every problem it finds at once, the
same discipline every other registry follows.

## What this is not

- **No agent runtime, no LLM/Copilot API calls, no execution of any `Tool`
  action, ever, from this module** — `copilot_code_review` is catalog data;
  nothing in `engines/composition` invokes it. Phase 7 (`docs/agent-runtime.md`)
  adds a separate, opt-in runtime that *simulates* tool execution — still no
  real `Tool` action call anywhere in this codebase.
- **No Evaluation Harness / trust score / evaluation execution** —
  `Evaluation`/`EvaluationSuite`/`MetricResult` (Phase 1,
  `domain/metamodel/entities/evaluation/evaluation.py`) are untouched and not
  wired into `engines/composition`. `CandidateAssessment.coverage` is
  explicitly not a certification or trust score.
- **No API, no UI, no orchestration, and no Marketplace *Service*** — only
  catalog data plus a pure resolution engine. Nothing here is reachable over
  a network.
- **No write path** — `engines/composition` never calls `ProjectGraphService`
  or any persistence port. Persisting a specific project's staffing decision
  (an `IMPLEMENTED_BY` edge scoped to one project) is future orchestrator
  work.
- **No `Policy` registry / `policies.yaml`** — `Agent.policies` stays `[]`
  across the whole worked catalog.
- **No cross-validation of `EngineeringRole.required_skills`/`required_tools`/
  `required_knowledge` against the new catalogs** — deliberately, so the 7
  "catalogued, not staffed" roles' skill/tool/knowledge keys don't have to be
  populated this phase.
- **No changes to the already-reviewed worked delivery model**
  (`metamodel-registry/delivery-models/data-engineering.yaml`) — the
  marketplace catalog is strictly additive under `metamodel-registry/`.
- **No live Copilot code review, GitHub Models call, or Copilot coding agent
  execution** — all three deferred integration points land as registry/schema
  facts only.
- **No agent certification/deployment lifecycle transitions run** — every
  worked agent sits at `DRAFT`/`CANDIDATE`; nothing in this phase promotes
  them through `AgentLifecycle`.
