"""Marketplace resolution: matching registry agents against engineering roles.

A pure, catalog-wide layer over an existing, already-tested primitive --
``EngineeringRole.is_satisfied_by()``/``missing_requirements()``
(``domain/metamodel/entities/organization/roles.py``) -- which this module
calls, and does not reimplement. Distinct from, and complementary to,
``DeliveryContract.conformance_of()`` (``domain/metamodel/entities/delivery/
contracts.py``), which answers a narrower, task-level question about one
already-identified agent. This module answers the marketplace question: given
a role and a catalog, which agents satisfy it, and how close do the rest come?

Pure: no I/O, no persistence, no ``ProjectGraphService``. Composition reasons
over registry catalog data only -- it never resolves a project-specific
``IMPLEMENTED_BY`` edge. See ``docs/marketplace.md``.
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import Field

from domain.metamodel.base import MetamodelModel
from domain.metamodel.entities.organization import Agent, EngineeringRole
from domain.metamodel.enums import AgentLifecycle
from domain.metamodel.registry import MetamodelRegistry


class CandidateAssessment(MetamodelModel):
    """How one agent measures up against one role.

    Not a certification score -- coverage is a resolution-time signal over
    declared capability, computed the same way ``GateReadiness``'s dimension
    score treats "requires nothing" as trivially complete
    (``engines/gates/readiness.py``). It says nothing about whether the agent
    has been evaluated.
    """

    agent_key: str
    role_key: str
    status: AgentLifecycle
    satisfies: bool
    missing: dict[str, list[str]]
    coverage: float = Field(ge=0.0, le=1.0)

    def explain(self) -> str:
        if self.satisfies:
            return f"{self.agent_key} satisfies {self.role_key}"
        gaps = "; ".join(
            f"{dimension}: {', '.join(keys)}" for dimension, keys in self.missing.items() if keys
        ) or "unspecified"
        return f"{self.agent_key} does not satisfy {self.role_key} -- {gaps}"


class RoleResolution(MetamodelModel):
    """The result of resolving one role against a candidate pool."""

    role_key: str
    matches: list[CandidateAssessment] = Field(default_factory=list)
    near_misses: list[CandidateAssessment] = Field(default_factory=list)

    @property
    def is_staffable(self) -> bool:
        return bool(self.matches)

    @property
    def best_match(self) -> CandidateAssessment | None:
        return self.matches[0] if self.matches else None


def _coverage(role: EngineeringRole, missing: dict[str, list[str]]) -> float:
    """Fraction of the role's required keys the agent already holds.

    A role requiring nothing in a dimension is trivially fully covered in it
    -- the same "empty is complete" idiom ``engines/gates/readiness.py`` uses.
    """
    required_by_dimension = {
        "capabilities": role.required_capabilities,
        "delivery_capabilities": role.required_delivery_capabilities,
        "skills": role.required_skills,
        "tools": role.required_tools,
        "knowledge": role.required_knowledge,
    }
    total = sum(len(v) for v in required_by_dimension.values())
    if total == 0:
        return 1.0
    still_missing = sum(len(v) for v in missing.values())
    return max(0.0, (total - still_missing) / total)


def assess_candidate(role: EngineeringRole, agent: Agent) -> CandidateAssessment:
    """Score one agent against one role.

    A thin wrapper over ``EngineeringRole.is_satisfied_by()``/
    ``missing_requirements()`` -- it does not recompute what those already
    compute.
    """
    kwargs = {
        "capabilities": set(agent.capabilities),
        "delivery_capabilities": set(agent.delivery_capabilities),
        "skills": set(agent.skills),
        "tools": set(agent.tools),
        "knowledge": set(agent.knowledge_packs),
    }
    missing = role.missing_requirements(**kwargs)
    return CandidateAssessment(
        agent_key=agent.agent_key,
        role_key=role.role_key,
        status=agent.status,
        satisfies=role.is_satisfied_by(**kwargs),
        missing=missing,
        coverage=_coverage(role, missing),
    )


def resolve_role(
    role: EngineeringRole,
    candidates: Iterable[Agent],
    *,
    strict_role_match: bool = True,
) -> RoleResolution:
    """Assess every candidate against one role, partitioned and ranked.

    ``strict_role_match=True`` (the default) considers only agents that
    declare ``role_key == role.role_key`` -- ``IMPLEMENTED_BY``'s own
    semantics: an agent is built to implement one specific role. Setting it
    ``False`` widens the search to the whole candidate pool regardless of
    declared role, for the (also real) question "does anything already in the
    catalog happen to cover this gap," at the cost of considering agents
    nobody built or versioned for this role.
    """
    pool = [
        agent for agent in candidates if not strict_role_match or agent.role_key == role.role_key
    ]
    assessments = [assess_candidate(role, agent) for agent in pool]

    def _rank(assessment: CandidateAssessment) -> tuple[float, str]:
        return (-assessment.coverage, assessment.agent_key)

    return RoleResolution(
        role_key=role.role_key,
        matches=sorted((a for a in assessments if a.satisfies), key=_rank),
        near_misses=sorted((a for a in assessments if not a.satisfies), key=_rank),
    )


def resolve_catalog(registry: MetamodelRegistry) -> dict[str, RoleResolution]:
    """Resolve every engineering role in the registry against its own agent catalog.

    The one function in this module that touches ``MetamodelRegistry``
    directly -- everything else takes plain domain objects, matching how
    ``engines.impact.analyze_impact()`` takes a ``LoadedDeliveryModel`` rather
    than a registry.
    """
    return {
        key: resolve_role(role, registry.agents.values())
        for key, role in registry.engineering_roles.items()
    }
