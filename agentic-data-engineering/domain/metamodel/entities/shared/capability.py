"""Problem, Requirement, Capability, DeliveryCapability and CapabilityGap.

Two kinds of capability, deliberately distinct entities rather than one with a
flag:

* **Capability** -- what the technical system does. Streaming, CDC, lineage.
* **DeliveryCapability** -- what the organization's process assures. Change
  Assurance, Release Assurance, Operational Readiness (§16).

They are discovered from different evidence (code versus documentation), they
have different maturity semantics, and a project routinely scores high on one
and low on the other -- which is exactly the finding the platform exists to
surface. Collapsing them into one type with a discriminator would make that
comparison awkward and would let a technical capability satisfy a delivery
requirement by accident.

``CapabilityGap`` is shared, referencing either kind through an ``EntityRef``.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from domain.metamodel.base import EntityRef, ProvenancedEntity
from domain.metamodel.enums import EntityType, RiskClass, Twin


class Problem(ProvenancedEntity):
    """Something about the project that needs solving."""

    entity_type: EntityType = EntityType.PROBLEM
    twin: Twin = Twin.SHARED

    project_ref: EntityRef
    statement: str = Field(min_length=1)
    business_impact: str | None = None
    severity: RiskClass = RiskClass.MEDIUM
    raised_by: str | None = None
    required_capability_keys: list[str] = Field(default_factory=list)
    required_delivery_capability_keys: list[str] = Field(default_factory=list)


class Requirement(ProvenancedEntity):
    """A specific, verifiable thing the solution must do.

    The head of the traceability chain (§27): Requirement → DeliveryTask →
    Agent → Artifact → Test → Evidence → Approval → Deployment.
    """

    entity_type: EntityType = EntityType.REQUIREMENT
    twin: Twin = Twin.SHARED

    project_ref: EntityRef
    statement: str = Field(min_length=1)
    requirement_kind: str = Field(default="functional", description="functional | non_functional")
    acceptance_criteria: list[str] = Field(default_factory=list)
    priority: str | None = None
    source_refs: list[EntityRef] = Field(
        default_factory=list, description="Where this came from. Uncited requirements fail a gate."
    )
    capability_keys: list[str] = Field(default_factory=list)
    #: Delivery tasks that implement this requirement.
    traced_to_task_keys: list[str] = Field(default_factory=list)


class Capability(ProvenancedEntity):
    """A technical capability the project exercises, as observed.

    The catalog of capability *types* is registry data; this is an instance
    found in a specific project, with the evidence that says so.
    """

    entity_type: EntityType = EntityType.CAPABILITY
    twin: Twin = Twin.TECHNICAL

    project_ref: EntityRef
    capability_key: str = Field(min_length=1)
    maturity: int = Field(
        default=0,
        ge=0,
        le=5,
        description="0 absent, 1 ad hoc, 2 repeatable, 3 defined, 4 managed, 5 optimizing.",
    )
    supporting_refs: list[EntityRef] = Field(default_factory=list)


class DeliveryCapability(ProvenancedEntity):
    """An assurance capability the organization's delivery process provides.

    Change Assurance, Regression Assurance, Release Assurance, Operational
    Readiness, Compliance Assurance and so on. Discovered from delivery
    documentation and from what the gates actually require -- a process that
    claims Security Assurance but has no security gate scores low regardless of
    what the handbook says.
    """

    entity_type: EntityType = EntityType.DELIVERY_CAPABILITY
    twin: Twin = Twin.DELIVERY

    project_ref: EntityRef
    delivery_capability_key: str = Field(min_length=1)
    maturity: int = Field(default=0, ge=0, le=5)
    #: Gates, checklists and controls that evidence this capability.
    supporting_refs: list[EntityRef] = Field(default_factory=list)
    #: Engineering role keys the platform would need to staff to provide it.
    realized_by_role_keys: list[str] = Field(default_factory=list)


class CapabilityGap(ProvenancedEntity):
    """The distance between what exists and what should.

    Shared across both twins: ``capability_ref`` points at either a Capability
    or a DeliveryCapability, and ``twin`` records which dimension the gap is in
    so a project can be told "your pipelines are excellent and your change
    assurance is absent".
    """

    entity_type: EntityType = EntityType.CAPABILITY_GAP
    twin: Twin = Twin.SHARED

    project_ref: EntityRef
    #: Points at a Capability or a DeliveryCapability.
    capability_ref: EntityRef
    capability_key: str = Field(min_length=1)
    current_maturity: int = Field(ge=0, le=5)
    desired_maturity: int = Field(ge=0, le=5)
    risk: RiskClass = RiskClass.MEDIUM
    priority: int = Field(default=3, ge=1, le=5, description="1 is highest.")
    recommendation: str | None = None
    recommended_role_keys: list[str] = Field(default_factory=list)

    @property
    def gap_size(self) -> int:
        return max(0, self.desired_maturity - self.current_maturity)

    @property
    def is_delivery_gap(self) -> bool:
        return self.capability_ref.type is EntityType.DELIVERY_CAPABILITY

    @model_validator(mode="after")
    def _must_be_a_real_gap(self) -> CapabilityGap:
        if self.desired_maturity < self.current_maturity:
            raise ValueError(
                "desired_maturity below current_maturity is not a gap; record a Finding if the "
                "project is over-engineered for its needs."
            )
        if self.capability_ref.type not in (
            EntityType.CAPABILITY,
            EntityType.DELIVERY_CAPABILITY,
        ):
            raise ValueError(
                f"capability_ref must point at a Capability or DeliveryCapability, got "
                f"{self.capability_ref.type.value}"
            )
        return self
