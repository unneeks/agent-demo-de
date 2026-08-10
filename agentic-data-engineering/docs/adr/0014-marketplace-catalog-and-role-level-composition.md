# ADR-0014: Marketplace catalog and role-level composition, reusing existing role-satisfaction logic

**Status:** Accepted · **Date:** 2026-08-09 · **Phase:** 4

## Context

`EngineeringRole.is_satisfied_by()`/`missing_requirements()`
(`domain/metamodel/entities/organization/roles.py`) has existed since Phase 1
and is already tested against hand-built `Agent` fixtures
(`tests/unit/test_acceptance_criteria.py`), but no registry catalog has ever
called it with real data. `Agent`, `Skill`, `Tool` and `KnowledgePack`
(`domain/metamodel/entities/organization/agents.py`) are fully modeled with no
YAML catalog, unlike capabilities, engineering roles, delivery roles and
platforms, which have loaded from `metamodel-registry/` since Phase 1.

Separately, `docs/adr/README.md`'s "Deferred, and why" section named three
specific, still-unstarted GitHub Copilot integration points: Copilot code
review as a marketplace `Tool`, GitHub Models behind the configurable model
provider, and Copilot coding agent as an `EXTERNAL_AGENT` implementation of an
`EngineeringRole` — the last explicitly flagged as needing "an `EXTERNAL_AGENT`
execution model and a provider binding on `Agent`, a known, accepted refactor."

## Decision

**Four new registry catalogs** (`skills.yaml`, `tools.yaml`,
`knowledge_packs.yaml`, `agents.yaml`), loaded by `MetamodelRegistry` the same
way every existing registry is, scoped deliberately to the 5 engineering
roles marked "staffed in the MVP" in `engineering_roles.yaml`
(`regression-engineer`, `impact-analysis-engineer`, `data-quality-engineer`,
`data-model-engineer`, `delivery-compliance-engineer`) rather than all 12.

**A new engine, `engines/composition/`, that reuses `is_satisfied_by()`/
`missing_requirements()` rather than reimplementing role-satisfaction logic.**
`assess_candidate()` is a thin wrapper; `resolve_role()`/`resolve_catalog()`
add catalog-wide framing (partition into matches/near-misses, rank by
coverage) on top. Explicitly distinguished from `DeliveryContract
.conformance_of()`, which already exists and answers a narrower, task-level
question about one already-identified agent — composition answers "which
agents in the whole catalog satisfy this role, and how close do the rest
come," a genuinely different operation, not a duplicate of the same one.

**The three deferred Copilot integration points land as registry/schema data
only**, no live call:

- Copilot code review as a marketplace `Tool` action (`github.
  copilot_code_review`, `LOW_RISK_WRITE`, findings framed as
  `Evidence(evidence_kind="review_record")`).
- GitHub Models behind the configurable model provider — investigated and
  found to need **no code change**: `Agent.model_provider`/`model_name` were
  already free-form strings "the runtime resolves." The worked catalog's
  `data-quality-agent` uses `model_provider: github-models` as proof the field
  already accepts it.
- Copilot coding agent as `EXTERNAL_AGENT` — `ExecutionModel` gains
  `EXTERNAL_AGENT`, and `Agent` gains `external_provider: str | None` plus a
  validator requiring it whenever `execution_model is EXTERNAL_AGENT`. This is
  the concrete "provider binding on `Agent`" ADR-0009's forward note flagged.

## Consequences

**Good.** `is_satisfied_by()`/`missing_requirements()` finally has real data
proving it works end to end — five roles staffed, one deliberately incomplete
agent proving the gap-reporting path. The "provider binding" refactor lands
as one field and one validator in the same file, in the same style as the
existing `ToolAction._dangerous_actions_need_approval` validator, not a
restructuring of `Agent`. The GitHub Models integration point turned out to
need nothing — worth stating plainly rather than silently doing nothing and
leaving the question open.

**Costs, stated honestly.** The catalog only covers 5 of 12 engineering roles
— the other 7 ("catalogued, not staffed") have no agents and are not
cross-validated against the new catalogs at all, so a broken skill/tool
reference on one of those roles would not be caught by `registry.validate()`
today. There is no write path from a `RoleResolution` to a project's graph:
binding a specific resolved agent to a specific project's `IMPLEMENTED_BY`
edge is future orchestrator-layer work, not built here. `Agent.policies` and
a `policies.yaml` catalog remain a named gap — every worked agent carries an
empty policy list.

## Alternatives rejected

**Reusing `DeliveryContract.conformance_of()` directly instead of a new
engine.** Rejected: it requires an already-identified single agent and a
specific task/contract; it cannot answer "which agents in the whole catalog
satisfy this role," which needs to iterate the catalog and rank results.

**Overloading `model_provider` for `EXTERNAL_AGENT` instead of adding
`external_provider`.** Rejected: the two fields make semantically different
claims. `model_provider` describes which LLM this platform's own runtime
would call if it executed the agent itself; that claim does not apply when an
external system owns the whole execution loop and this platform never picks a
model. Conflating them would make a `PLANNER_EXECUTOR` agent's
`model_provider` field mean two different things depending on
`execution_model`.

**Symmetric validation: every `EngineeringRole`'s required skill/tool/
knowledge key must exist in the new catalogs.** Rejected for this phase: it
would force populating catalog entries for all 7 "catalogued, not staffed"
roles too, expanding scope past the 5 roles this phase's worked catalog
actually proves out end to end. A follow-up once those roles get their own
worked agents.

**Recording the delivery model changes needed to fully wire the
`copilot_code_review` Evidence pipeline** (a new `EvidenceRequirement` on the
worked delivery model). Rejected: the already-reviewed
`metamodel-registry/delivery-models/data-engineering.yaml` stays untouched
this phase; the evidence framing is demonstrated by a standalone `Evidence`
instance in a unit test instead.
