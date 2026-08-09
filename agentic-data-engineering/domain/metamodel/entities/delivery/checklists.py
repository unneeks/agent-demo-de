"""Checklists, checklist items, waivers and acceptance criteria.

A checklist here is a structured object, never a text blob. That is the whole
point of the addendum: a control the platform cannot evaluate is a control the
platform cannot enforce.

Two things are deliberately kept apart:

* **Checklists** verify that the work was *done properly* -- process compliance.
* **Acceptance criteria** verify that the output is *correct* -- product quality.

They are often conflated in real delivery documentation, and separating them is
what lets an agent be judged on both independently (§28).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from domain.metamodel.base import (
    Blockable,
    EntityRef,
    MetamodelModel,
    ProvenancedEntity,
    utc_now,
)
from domain.metamodel.enums import (
    ChecklistItemStatus,
    CompletionRule,
    EntityType,
    MACHINE_EVALUABLE,
    Severity,
    Twin,
    ValidationMethod,
)


class Waiver(MetamodelModel):
    """A deliberate, attributed decision to proceed despite an unmet control.

    Every field is required. An unattributed waiver is indistinguishable from a
    skipped control, and a waiver with no evidence is indistinguishable from an
    opinion -- which is precisely how governance quietly stops meaning anything.
    """

    reason: str = Field(min_length=1, max_length=4000)
    approver: str = Field(min_length=1)
    waived_at: datetime = Field(default_factory=utc_now)
    evidence_ref: EntityRef
    expires_at: datetime | None = Field(
        default=None, description="Waivers should be temporary; None means indefinite."
    )

    @property
    def is_expired(self) -> bool:
        return self.expires_at is not None and self.expires_at < utc_now()


class ChecklistItem(ProvenancedEntity, Blockable):
    """One control within a checklist.

    ``Blockable`` applies: an item extracted from a document by an LLM cannot be
    ``blocking=True`` until a human has verified it. Extracted process text may
    advise; only verified process text may stop a release. See ADR-0009.
    """

    entity_type: EntityType = EntityType.CHECKLIST_ITEM
    twin: Twin = Twin.DELIVERY

    item_key: str = Field(min_length=1)
    checklist_key: str = Field(min_length=1)
    sequence: int = Field(default=0, ge=0)
    mandatory: bool = True
    validation_method: ValidationMethod = ValidationMethod.HUMAN_REVIEW
    evidence_required: bool = False
    #: Where an automated check can be found, when the method is machine-evaluable.
    validation_reference: str | None = None
    guidance: str | None = None

    @property
    def is_machine_evaluable(self) -> bool:
        """Whether an agent can discharge this without a human."""
        return self.validation_method in MACHINE_EVALUABLE

    @model_validator(mode="after")
    def _automated_items_need_a_reference(self) -> ChecklistItem:
        if self.validation_method is ValidationMethod.AUTOMATED and not self.validation_reference:
            raise ValueError(
                f"checklist item {self.item_key!r} claims AUTOMATED validation but names no "
                "validation_reference; an automated check nobody can locate is a manual check."
            )
        return self


class ChecklistItemResult(MetamodelModel):
    """The outcome of evaluating one item on one occasion.

    Runtime state rather than definition, so it is a value object persisted with
    its outcome rather than a separately versioned entity.
    """

    item_key: str = Field(min_length=1)
    status: ChecklistItemStatus = ChecklistItemStatus.PENDING
    evidence_refs: list[EntityRef] = Field(default_factory=list)
    waiver: Waiver | None = None
    note: str | None = None
    evaluated_at: datetime = Field(default_factory=utc_now)
    evaluated_by: str | None = None

    @model_validator(mode="after")
    def _waived_requires_a_waiver(self) -> ChecklistItemResult:
        if self.status is ChecklistItemStatus.WAIVED and self.waiver is None:
            raise ValueError(
                f"item {self.item_key!r} is marked WAIVED but carries no waiver. A waiver "
                "requires a reason, an approver, a timestamp and evidence."
            )
        if self.status is not ChecklistItemStatus.WAIVED and self.waiver is not None:
            raise ValueError(
                f"item {self.item_key!r} carries a waiver but its status is "
                f"{self.status.value}; a waiver only makes sense on a WAIVED item."
            )
        return self


class Checklist(ProvenancedEntity):
    """A structured set of controls applied to a task, phase or gate."""

    entity_type: EntityType = EntityType.CHECKLIST
    twin: Twin = Twin.DELIVERY

    checklist_key: str = Field(min_length=1)
    #: Task or phase keys this checklist validates.
    applies_to: list[str] = Field(default_factory=list)
    item_refs: list[EntityRef] = Field(default_factory=list)
    completion_rule: CompletionRule = CompletionRule.ALL_MANDATORY
    #: Required when completion_rule is PERCENTAGE.
    completion_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    owner: str | None = None

    @model_validator(mode="after")
    def _percentage_rule_needs_a_threshold(self) -> Checklist:
        if self.completion_rule is CompletionRule.PERCENTAGE and self.completion_threshold is None:
            raise ValueError(
                f"checklist {self.checklist_key!r} uses the PERCENTAGE completion rule but sets "
                "no completion_threshold; 'mostly complete' is not a rule."
            )
        return self


class AcceptanceCriterion(ProvenancedEntity, Blockable):
    """A condition the *output* must satisfy to be accepted.

    Machine-evaluable wherever possible -- ``AC-LDM-07`` ("every logical entity
    must have an identified business owner") is a metadata lookup, not a matter
    of opinion, and modelling it as one is what lets an agent discharge it.
    """

    entity_type: EntityType = EntityType.ACCEPTANCE_CRITERION
    twin: Twin = Twin.DELIVERY

    criterion_key: str = Field(min_length=1)
    condition: str = Field(min_length=1)
    validation_method: ValidationMethod = ValidationMethod.HUMAN_REVIEW
    validation_reference: str | None = None
    severity: Severity = Severity.MEDIUM
    applies_to: list[str] = Field(
        default_factory=list, description="Task or output keys this criterion judges."
    )
    evidence_required: bool = True

    @property
    def is_machine_evaluable(self) -> bool:
        return self.validation_method in MACHINE_EVALUABLE

    @model_validator(mode="after")
    def _critical_criteria_must_block(self) -> AcceptanceCriterion:
        """A CRITICAL criterion that does not block is decorative.

        Rather than silently allowing it, force the author to say what they
        mean: either lower the severity or accept that it blocks.
        """
        if self.severity is Severity.CRITICAL and not self.blocking:
            raise ValueError(
                f"criterion {self.criterion_key!r} is CRITICAL but blocking=False. Either it "
                "stops delivery or it is not critical."
            )
        return self


class DefinitionOfDone(ProvenancedEntity):
    """The organization's standing bar for 'finished'.

    Distinct from a task's acceptance criteria: those are specific to one
    output, this applies across a phase or model.
    """

    entity_type: EntityType = EntityType.DEFINITION_OF_DONE
    twin: Twin = Twin.DELIVERY

    dod_key: str = Field(min_length=1)
    applies_to: list[str] = Field(default_factory=list)
    criterion_refs: list[EntityRef] = Field(default_factory=list)
    statements: list[str] = Field(
        default_factory=list,
        description="Free-text conditions not yet decomposed into criteria.",
    )
