"""DeliveryTask, DeliveryActivity, and the input/output specifications.

A DeliveryTask is not documentation. It is an executable contract for
engineering work: it names what it needs, what it must produce, which checklist
validates it, which criteria it is judged against and which gate it feeds. An
agent claiming it is claiming all of that.

``DeliveryInput`` and ``DeliveryOutput`` are *specifications*, not artifact
instances. "This task requires a Business Requirements document" is a durable
statement about the process; the actual document that satisfies it on a given
project is a ``DeliveryArtifact``. Conflating them would make it impossible to
ask the useful question -- which required inputs are missing.
"""

from __future__ import annotations

from pydantic import Field

from domain.metamodel.base import EntityRef, ProvenancedEntity
from domain.metamodel.enums import EntityType, RiskClass, Twin


class DeliveryInput(ProvenancedEntity):
    """A specification of something a task requires before it can start."""

    entity_type: EntityType = EntityType.DELIVERY_INPUT
    twin: Twin = Twin.DELIVERY

    input_key: str = Field(min_length=1)
    #: What kind of thing satisfies this: requirement | architecture | dataset |
    #: code | data_model | policy | template | decision | artifact
    input_kind: str = Field(min_length=1)
    mandatory: bool = True
    #: Artifact type key that satisfies this input, when the model names one.
    satisfied_by_artifact_kind: str | None = None
    source_phase_key: str | None = Field(
        default=None, description="Phase that normally produces this input."
    )


class DeliveryOutput(ProvenancedEntity):
    """A specification of something a task must produce."""

    entity_type: EntityType = EntityType.DELIVERY_OUTPUT
    twin: Twin = Twin.DELIVERY

    output_key: str = Field(min_length=1)
    output_kind: str = Field(min_length=1)
    mandatory: bool = True
    artifact_kind: str | None = None
    template_ref: EntityRef | None = None
    #: Evidence requirements this output must satisfy to count as delivered.
    evidence_requirement_refs: list[EntityRef] = Field(default_factory=list)


class DeliveryTask(ProvenancedEntity):
    """A unit of work in the organization's delivery process."""

    entity_type: EntityType = EntityType.DELIVERY_TASK
    twin: Twin = Twin.DELIVERY

    task_key: str = Field(min_length=1)
    phase_keys: list[str] = Field(default_factory=list)
    purpose: str | None = None

    input_refs: list[EntityRef] = Field(default_factory=list)
    output_refs: list[EntityRef] = Field(default_factory=list)
    activity_refs: list[EntityRef] = Field(default_factory=list)

    #: What an implementation must bring. Skills are marketplace slugs; the
    #: role keys are *delivery* roles -- who is accountable in the organization.
    required_skill_keys: list[str] = Field(default_factory=list)
    required_tool_keys: list[str] = Field(default_factory=list)
    delivery_role_keys: list[str] = Field(default_factory=list)

    checklist_refs: list[EntityRef] = Field(default_factory=list)
    acceptance_criterion_refs: list[EntityRef] = Field(default_factory=list)
    approval_gate_refs: list[EntityRef] = Field(default_factory=list)
    evidence_requirement_refs: list[EntityRef] = Field(default_factory=list)
    definition_of_done_ref: EntityRef | None = None
    standard_refs: list[EntityRef] = Field(default_factory=list)

    risk_level: RiskClass = RiskClass.MEDIUM
    #: Whether an agent may perform this unattended once certified. Some tasks
    #: are irreducibly human regardless of agent capability.
    automatable: bool = True

    @property
    def mandatory_control_refs(self) -> list[EntityRef]:
        """Every control an implementation must satisfy to claim this task.

        Used by composition to reject an agent that can do the work but does not
        cover the organization's controls for it.
        """
        return [*self.checklist_refs, *self.acceptance_criterion_refs, *self.approval_gate_refs]


class DeliveryActivity(ProvenancedEntity):
    """A step within a task.

    Finer grained than a task and usually not separately gated -- the level at
    which a runbook or work instruction is written.
    """

    entity_type: EntityType = EntityType.DELIVERY_ACTIVITY
    twin: Twin = Twin.DELIVERY

    activity_key: str = Field(min_length=1)
    task_key: str = Field(min_length=1)
    sequence: int = Field(default=0, ge=0)
    instructions: str | None = None
    required_skill_keys: list[str] = Field(default_factory=list)
    automatable: bool = True
