"""Standard, Control, Template, Methodology, RaciAssignment and DeliveryArtifact.

The reference layer of the delivery model: the rules work must follow, the
shapes it must take, and who is accountable for it.

``Standard`` and ``Control`` are both ``Blockable``, which is where the
addendum's warning bites hardest. These are exactly the entities an extraction
pipeline will produce in bulk from PDFs, and exactly the ones that would do most
damage if a misreading were treated as enforced policy.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from domain.metamodel.base import Blockable, EntityRef, ProvenancedEntity
from domain.metamodel.enums import (
    EntityType,
    RaciLetter,
    RiskClass,
    Twin,
    ValidationMethod,
)


class Standard(ProvenancedEntity, Blockable):
    """An organizational rule that work must conform to.

    Enterprise data standards, naming standards, security standards, coding
    standards -- the things a review checks against.
    """

    entity_type: EntityType = EntityType.STANDARD
    twin: Twin = Twin.DELIVERY

    standard_key: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    category: str | None = Field(
        default=None, description="data | security | naming | architecture | coding | operational"
    )
    authority: str | None = Field(default=None, description="Who owns and can change this.")
    applies_to: list[str] = Field(default_factory=list)
    validation_method: ValidationMethod = ValidationMethod.HUMAN_REVIEW
    validation_reference: str | None = None
    supersedes: list[str] = Field(default_factory=list)
    effective_from: str | None = None


class Control(ProvenancedEntity, Blockable):
    """A governance or regulatory control the delivery process implements.

    Distinct from a Standard: a standard says how work should look, a control is
    an obligation the organization must be able to evidence to someone else.
    """

    entity_type: EntityType = EntityType.CONTROL
    twin: Twin = Twin.DELIVERY

    control_key: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    control_family: str | None = Field(
        default=None, description="e.g. change-management, access-control, data-protection"
    )
    regulatory_reference: str | None = None
    risk_level: RiskClass = RiskClass.MEDIUM
    #: Delivery tasks and gates that implement this control. A control nothing
    #: implements is a finding in its own right.
    implemented_by: list[EntityRef] = Field(default_factory=list)
    evidence_requirement_refs: list[EntityRef] = Field(default_factory=list)
    test_frequency: str | None = None

    @model_validator(mode="after")
    def _critical_controls_must_be_evidenced(self) -> Control:
        if self.risk_level is RiskClass.CRITICAL and not self.evidence_requirement_refs:
            raise ValueError(
                f"control {self.control_key!r} is CRITICAL but requires no evidence; a control "
                "that cannot be evidenced cannot be demonstrated to an auditor."
            )
        return self


class Template(ProvenancedEntity):
    """A prescribed shape for a deliverable."""

    entity_type: EntityType = EntityType.TEMPLATE
    twin: Twin = Twin.DELIVERY

    template_key: str = Field(min_length=1)
    artifact_kind: str = Field(min_length=1)
    content_reference: str = Field(
        min_length=1, description="Where the template lives -- path, URI or document id."
    )
    required_sections: list[str] = Field(default_factory=list)
    owner: str | None = None


class Methodology(ProvenancedEntity):
    """The overarching delivery approach a model follows."""

    entity_type: EntityType = EntityType.METHODOLOGY
    twin: Twin = Twin.DELIVERY

    methodology_key: str = Field(min_length=1)
    style: str | None = Field(default=None, description="waterfall | agile | hybrid | safe")
    principles: list[str] = Field(default_factory=list)
    reference: str | None = None


class RaciAssignment(ProvenancedEntity):
    """Who is Responsible, Accountable, Consulted or Informed for a task."""

    entity_type: EntityType = EntityType.RACI_ASSIGNMENT
    twin: Twin = Twin.DELIVERY

    #: The task, phase or gate this assignment covers.
    subject_ref: EntityRef
    delivery_role_key: str = Field(min_length=1)
    letter: RaciLetter

    @property
    def is_accountable(self) -> bool:
        """Exactly one role should be accountable; the registry validator checks it."""
        return self.letter is RaciLetter.ACCOUNTABLE


class DeliveryArtifact(ProvenancedEntity):
    """A concrete deliverable produced by delivery work.

    The bridge between the twins. A DeliveryArtifact ``DESCRIBES`` technical
    entities: an architecture document describes ArchitectureElements, a logical
    data model describes DataAssets. That edge is what makes
    "is this document still true?" answerable, and it is what
    ``documentation drift`` detection will hang off in a later phase.
    """

    entity_type: EntityType = EntityType.DELIVERY_ARTIFACT
    twin: Twin = Twin.DELIVERY

    artifact_key: str = Field(min_length=1)
    artifact_kind: str = Field(min_length=1)
    project_ref: EntityRef | None = None
    produced_by_task_key: str | None = None
    template_ref: EntityRef | None = None
    content_reference: str | None = None
    content_hash: str | None = None
    #: Technical entities this artifact documents.
    describes_refs: list[EntityRef] = Field(default_factory=list)
    #: The output specification this artifact satisfies.
    satisfies_output_key: str | None = None
    status: str = Field(default="draft", description="draft | review | approved | superseded")
    approved_by: str | None = None

    @model_validator(mode="after")
    def _approved_artifacts_name_their_approver(self) -> DeliveryArtifact:
        if self.status == "approved" and not self.approved_by:
            raise ValueError(
                f"artifact {self.artifact_key!r} is marked approved but names no approver."
            )
        return self
