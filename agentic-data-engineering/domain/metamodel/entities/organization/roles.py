"""The four-level role chain.

::

    DeliveryRole ──▶ EngineeringResponsibility ──▶ EngineeringRole ──▶ Agent
    who is accountable   what must be              what engineering    what software
    in the org's process answered for              function does it    performs it

Why four levels and not two. A *DeliveryRole* is an organizational fact: "Data
Architect" appears in the RACI, signs the architecture gate, and exists whether
or not this platform does. An *EngineeringRole* is a marketplace abstraction:
the unit an agent implements and an evaluation certifies. They are frequently
named the same thing and are frequently not the same thing -- one delivery role
often carries several responsibilities, and one responsibility is often shared
across delivery roles.

``EngineeringResponsibility`` is the join that makes that expressible. Without
it the mapping is many-to-many with no name for what is being mapped, and the
first time an organization splits a role the model needs surgery. See ADR-0009.
"""

from __future__ import annotations

from pydantic import Field

from domain.metamodel.base import EntityRef, MetamodelEntity, ProvenancedEntity
from domain.metamodel.enums import (
    ApprovalLevel,
    AutomationLevel,
    EntityType,
    RiskClass,
    Twin,
)


class DeliveryRole(ProvenancedEntity):
    """A role in the organization's delivery process.

    Discovered from delivery documentation -- RACI tables, gate definitions,
    process documents -- hence provenanced. It describes accountability, not
    capability.
    """

    entity_type: EntityType = EntityType.DELIVERY_ROLE
    twin: Twin = Twin.DELIVERY

    role_key: str = Field(min_length=1)
    #: Responsibility keys this role is accountable for.
    responsibility_keys: list[str] = Field(default_factory=list)
    #: Gates this role is empowered to approve. The authority half of the role.
    approves_gate_keys: list[str] = Field(default_factory=list)
    accountable_for_task_keys: list[str] = Field(default_factory=list)
    reports_to: str | None = None
    is_segregated: bool = Field(
        default=False,
        description="Whether segregation of duties forbids combining this with the roles below.",
    )
    incompatible_with: list[str] = Field(
        default_factory=list,
        description="Role keys the same person may not simultaneously hold.",
    )


class EngineeringResponsibility(MetamodelEntity):
    """A discrete thing that must be answered for.

    The stable middle of the chain. A delivery role is accountable for
    responsibilities; an engineering role fulfils them; an agent implements the
    engineering role. Because responsibilities are named, an organization can
    reshuffle its delivery roles without invalidating the agent ecosystem.
    """

    entity_type: EntityType = EntityType.ENGINEERING_RESPONSIBILITY
    twin: Twin = Twin.SHARED

    responsibility_key: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    #: Technical and delivery capability keys this responsibility demands.
    required_capability_keys: list[str] = Field(default_factory=list)
    required_delivery_capability_keys: list[str] = Field(default_factory=list)
    #: Engineering role keys that can fulfil this. Many-to-many by design.
    fulfilled_by_role_keys: list[str] = Field(default_factory=list)
    risk_level: RiskClass = RiskClass.MEDIUM
    #: Whether this responsibility may ever be discharged without a human.
    #: Some accountability is not delegable regardless of agent quality.
    delegable_to_agent: bool = True


class EngineeringRole(MetamodelEntity):
    """A required engineering function, stated independently of who performs it.

    The stable abstraction agents are composed against and evaluations certify.
    Workflows and contracts bind to role keys, never to agent ids, so replacing
    an agent touches one edge.
    """

    entity_type: EntityType = EntityType.ENGINEERING_ROLE
    twin: Twin = Twin.SHARED

    role_key: str = Field(min_length=1)
    mission: str = Field(min_length=1)
    responsibilities: list[str] = Field(
        default_factory=list, description="EngineeringResponsibility keys this role fulfils."
    )

    # What an implementation must bring.
    required_capabilities: list[str] = Field(default_factory=list)
    required_delivery_capabilities: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    required_knowledge: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)

    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    policy_refs: list[EntityRef] = Field(default_factory=list)

    kpis: list[str] = Field(default_factory=list)
    evaluation_criteria: list[str] = Field(default_factory=list)
    minimum_evaluation_score: float = Field(default=0.8, ge=0.0, le=1.0)
    #: Separate bar for delivery conformance. An agent may be technically
    #: excellent and still fail this, which is the whole point of §28.
    minimum_delivery_conformance: float = Field(default=0.9, ge=0.0, le=1.0)

    risk_level: RiskClass = RiskClass.MEDIUM
    automation_level: AutomationLevel = AutomationLevel.ASSISTED
    default_approval_level: ApprovalLevel = ApprovalLevel.SINGLE_REVIEWER

    def is_satisfied_by(
        self,
        *,
        capabilities: set[str],
        skills: set[str],
        tools: set[str],
        knowledge: set[str] | None = None,
        delivery_capabilities: set[str] | None = None,
    ) -> bool:
        """Whether a candidate covers everything this role needs."""
        return (
            set(self.required_capabilities) <= capabilities
            and set(self.required_delivery_capabilities) <= (delivery_capabilities or set())
            and set(self.required_skills) <= skills
            and set(self.required_tools) <= tools
            and set(self.required_knowledge) <= (knowledge or set())
        )

    def missing_requirements(
        self,
        *,
        capabilities: set[str],
        skills: set[str],
        tools: set[str],
        knowledge: set[str] | None = None,
        delivery_capabilities: set[str] | None = None,
    ) -> dict[str, list[str]]:
        """Itemize what a candidate lacks, so a rejection can be explained."""
        return {
            "capabilities": sorted(set(self.required_capabilities) - capabilities),
            "delivery_capabilities": sorted(
                set(self.required_delivery_capabilities) - (delivery_capabilities or set())
            ),
            "skills": sorted(set(self.required_skills) - skills),
            "tools": sorted(set(self.required_tools) - tools),
            "knowledge": sorted(set(self.required_knowledge) - (knowledge or set())),
        }
