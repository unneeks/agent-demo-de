"""Marketplace resolution: matching registry agents against engineering roles.

A pure, catalog-wide layer over an existing, already-tested primitive --
``EngineeringRole.is_satisfied_by()``/``missing_requirements()``
(``domain/metamodel/entities/organization/roles.py``) -- which this module
calls, and does not reimplement. Complementary to, and now also a caller
of, ``DeliveryContract.conformance_of()`` (``domain/metamodel/entities/
delivery/contracts.py``): role satisfaction is still a catalog-wide,
capability-only question ("which agents in the whole marketplace satisfy
this role"), but when a caller supplies a real, project-and-task-specific
contract, ``resolve_role()`` also asks the narrower question
``conformance_of()`` was built to answer -- "can this one agent execute
this one task under the organization's process" -- and demotes a
role-satisfying-but-non-conformant agent out of ``matches``. See
``docs/marketplace.md`` and ADR-0020.

Pure: no I/O, no persistence, no ``ProjectGraphService``. Composition reasons
over registry catalog data (plus a caller-supplied ``DeliveryContract``,
itself plain data) only -- it never resolves a project-specific
``IMPLEMENTED_BY`` edge; that stays ``orchestrator/staffing.py``'s job.
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import Field

from domain.metamodel.base import MetamodelModel
from domain.metamodel.entities.delivery.contracts import ContractConformance, DeliveryContract
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
    #: Populated only when the caller supplied a DeliveryContract to
    #: resolve_role()/assess_candidate() -- role satisfaction and contract
    #: conformance are different questions, so this is additive, never a
    #: replacement for `satisfies`.
    conformance: ContractConformance | None = None

    def explain(self) -> str:
        if not self.satisfies:
            gaps = "; ".join(
                f"{dimension}: {', '.join(keys)}" for dimension, keys in self.missing.items() if keys
            ) or "unspecified"
            return f"{self.agent_key} does not satisfy {self.role_key} -- {gaps}"
        if self.conformance is not None and not self.conformance.is_eligible:
            reasons = "; ".join(str(gap) for gap in self.conformance.blocking_gaps) or "unspecified"
            return (
                f"{self.agent_key} satisfies {self.role_key} but does not conform to "
                f"{self.conformance.contract_key} -- {reasons}"
            )
        return f"{self.agent_key} satisfies {self.role_key}"


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


def assess_conformance(contract: DeliveryContract, agent: Agent) -> ContractConformance:
    """Score one agent against one delivery contract.

    A thin wrapper over ``DeliveryContract.conformance_of()`` -- it does not
    recompute what that already computes. Maps ``Agent.delivery``'s own
    declared fields (``supported_checklist_keys``/``supported_gate_keys``/
    ``supported_artifact_kinds``) to the delivery-side parameters
    ``conformance_of()`` needs -- the exact fields
    ``DeliveryCapabilityDeclaration`` exists to carry, unused until now.
    """
    return contract.conformance_of(
        agent_key=agent.agent_key,
        capabilities=set(agent.capabilities),
        skills=set(agent.skills),
        tools=set(agent.tools),
        knowledge=set(agent.knowledge_packs),
        supported_checklists=set(agent.delivery.supported_checklist_keys),
        supported_gates=set(agent.delivery.supported_gate_keys),
        supported_artifact_kinds=set(agent.delivery.supported_artifact_kinds),
    )


def assess_candidate(
    role: EngineeringRole, agent: Agent, *, contract: DeliveryContract | None = None
) -> CandidateAssessment:
    """Score one agent against one role, and -- when ``contract`` is
    supplied -- against that contract's delivery conformance too.

    A thin wrapper over ``EngineeringRole.is_satisfied_by()``/
    ``missing_requirements()`` (and, when ``contract`` is given,
    ``assess_conformance()``) -- it does not recompute what those already
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
        conformance=assess_conformance(contract, agent) if contract is not None else None,
    )


def resolve_role(
    role: EngineeringRole,
    candidates: Iterable[Agent],
    *,
    strict_role_match: bool = True,
    contract: DeliveryContract | None = None,
) -> RoleResolution:
    """Assess every candidate against one role, partitioned and ranked.

    ``strict_role_match=True`` (the default) considers only agents that
    declare ``role_key == role.role_key`` -- ``IMPLEMENTED_BY``'s own
    semantics: an agent is built to implement one specific role. Setting it
    ``False`` widens the search to the whole candidate pool regardless of
    declared role, for the (also real) question "does anything already in the
    catalog happen to cover this gap," at the cost of considering agents
    nobody built or versioned for this role.

    ``contract``, when supplied, is a real, project-and-task-specific
    ``DeliveryContract`` (e.g. from ``LoadedDeliveryModel.contract_for()``).
    A candidate that satisfies the role but cannot conform to the
    contract's mandatory controls is demoted out of ``matches`` into
    ``near_misses`` -- "an agent that is technically capable but cannot
    discharge the mandatory controls is rejected, with reasons" (the
    addendum's own framing). Leaving ``contract=None`` (the default)
    preserves this function's original role-only behaviour exactly.
    """
    pool = [
        agent for agent in candidates if not strict_role_match or agent.role_key == role.role_key
    ]
    assessments = [assess_candidate(role, agent, contract=contract) for agent in pool]

    def _rank(assessment: CandidateAssessment) -> tuple[float, str]:
        return (-assessment.coverage, assessment.agent_key)

    def _is_real_match(assessment: CandidateAssessment) -> bool:
        return assessment.satisfies and (
            assessment.conformance is None or assessment.conformance.is_eligible
        )

    return RoleResolution(
        role_key=role.role_key,
        matches=sorted((a for a in assessments if _is_real_match(a)), key=_rank),
        near_misses=sorted((a for a in assessments if not _is_real_match(a)), key=_rank),
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
