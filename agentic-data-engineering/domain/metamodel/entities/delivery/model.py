"""DeliveryModel, DeliveryPhase and DeliveryProcess.

A DeliveryModel is how an organization delivers a class of engineering work. The
platform must *discover* it from documentation rather than assume it: nothing
here presumes the phases are Discovery → Requirements → Architecture → …, and a
model with three phases or nineteen is equally representable.

``DeliveryProcess`` covers release, change and incident processes through a
``process_kind`` rather than three near-identical entity types. They differ in
their trigger and their gates, not in their shape, and keeping the kinds in the
registry means a new process type is a data change. See ADR-0010.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from domain.metamodel.base import EntityRef, ProvenancedEntity
from domain.metamodel.enums import EntityType, Twin


class DeliveryModel(ProvenancedEntity):
    """How an organization delivers a class of engineering work."""

    entity_type: EntityType = EntityType.DELIVERY_MODEL
    twin: Twin = Twin.DELIVERY

    model_key: str = Field(min_length=1)
    #: Which kinds of work this governs, e.g. ["data-engineering", "analytics"].
    applies_to: list[str] = Field(default_factory=list)
    methodology_ref: EntityRef | None = None
    #: Ordered by DeliveryPhase.sequence, not by position here.
    phase_refs: list[EntityRef] = Field(default_factory=list)
    process_refs: list[EntityRef] = Field(default_factory=list)
    owner: str | None = Field(default=None, description="Who owns this process definition.")
    #: Delivery capability keys this model claims to provide.
    delivery_capability_keys: list[str] = Field(default_factory=list)


class DeliveryPhase(ProvenancedEntity):
    """One stage of a delivery model.

    Entry and exit criteria are what make a phase more than a label: they are
    the conditions the platform evaluates to say whether work may start or
    finish, and they are why phase order can be checked rather than assumed.
    """

    entity_type: EntityType = EntityType.DELIVERY_PHASE
    twin: Twin = Twin.DELIVERY

    phase_key: str = Field(min_length=1)
    model_key: str = Field(min_length=1)
    sequence: int = Field(ge=0, description="Nominal order. Dependencies are authoritative.")
    purpose: str | None = None

    task_refs: list[EntityRef] = Field(default_factory=list)
    required_input_refs: list[EntityRef] = Field(default_factory=list)
    expected_output_refs: list[EntityRef] = Field(default_factory=list)
    required_role_keys: list[str] = Field(default_factory=list)
    checklist_refs: list[EntityRef] = Field(default_factory=list)
    approval_gate_refs: list[EntityRef] = Field(default_factory=list)

    entry_criteria: list[str] = Field(default_factory=list)
    exit_criteria: list[str] = Field(default_factory=list)
    policy_refs: list[EntityRef] = Field(default_factory=list)
    standard_refs: list[EntityRef] = Field(default_factory=list)
    template_refs: list[EntityRef] = Field(default_factory=list)
    evidence_requirement_refs: list[EntityRef] = Field(default_factory=list)

    #: Phase keys that must complete before this one may start. The registry
    #: validator checks this graph is acyclic -- a delivery model with a cycle
    #: is unsatisfiable and better caught at load than at run time.
    depends_on_phase_keys: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _phase_cannot_depend_on_itself(self) -> DeliveryPhase:
        if self.phase_key in self.depends_on_phase_keys:
            raise ValueError(f"phase {self.phase_key!r} cannot depend on itself")
        return self


class DeliveryProcess(ProvenancedEntity):
    """A named organizational process: release, change, incident and others.

    Distinct from DeliveryModel: a model describes how work is built, a process
    describes a recurring operational procedure that work must pass through.
    """

    entity_type: EntityType = EntityType.DELIVERY_PROCESS
    twin: Twin = Twin.DELIVERY

    process_key: str = Field(min_length=1)
    #: Registry-validated: release | change | incident | problem | ...
    process_kind: str = Field(min_length=1)
    trigger: str | None = Field(default=None, description="What starts this process.")
    phase_refs: list[EntityRef] = Field(default_factory=list)
    approval_gate_refs: list[EntityRef] = Field(default_factory=list)
    required_role_keys: list[str] = Field(default_factory=list)
    sla_hours: int | None = Field(default=None, ge=0)
    control_refs: list[EntityRef] = Field(default_factory=list)
