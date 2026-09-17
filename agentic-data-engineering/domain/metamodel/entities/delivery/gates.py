"""ApprovalGate, ApprovalRule, Approval and EvidenceRequirement.

A gate is the point where the delivery model actually bites. Everything else in
the Delivery Twin describes intent; a gate decides whether work proceeds.

Readiness is *computed* (see ``engines/gates/``), and deliberately separated
from the *decision*: the platform calculates what is and is not in place, and a
human decides what to do about it. Conflating the two would either let the
platform approve things or reduce it to a checklist nobody trusts.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from domain.metamodel.base import (
    Blockable,
    EntityRef,
    MetamodelEntity,
    ProvenancedEntity,
    new_ulid,
    utc_now,
)
from domain.metamodel.enums import (
    EntityType,
    GateDecision,
    RiskClass,
    Severity,
    Twin,
    ValidationMethod,
)


class EvidenceRequirement(ProvenancedEntity):
    """Something that must be produced and retained to prove work was done.

    The join between process and reality: a Test SATISFIES an EvidenceRequirement,
    which is how a technical test discharges an organizational control instead of
    the two living in separate worlds.
    """

    entity_type: EntityType = EntityType.EVIDENCE_REQUIREMENT
    twin: Twin = Twin.DELIVERY

    requirement_key: str = Field(min_length=1)
    evidence_kind: str = Field(
        min_length=1,
        description="test_result | review_record | approval | scan_report | model | runbook",
    )
    mandatory: bool = True
    applies_to: list[str] = Field(default_factory=list)
    validation_method: ValidationMethod = ValidationMethod.DOCUMENT_REVIEW
    retention_days: int | None = Field(default=None, ge=0)
    #: How the platform recognises evidence that satisfies this, when automatable.
    acceptance_pattern: str | None = None


class ApprovalRule(ProvenancedEntity, Blockable):
    """A condition that must hold for a gate to be passable.

    ``Blockable``: a rule inferred from a document cannot block until verified.
    """

    entity_type: EntityType = EntityType.APPROVAL_RULE
    twin: Twin = Twin.DELIVERY

    rule_key: str = Field(min_length=1)
    gate_key: str = Field(min_length=1)
    condition: str = Field(min_length=1)
    severity: Severity = Severity.MEDIUM
    validation_method: ValidationMethod = ValidationMethod.HUMAN_REVIEW
    validation_reference: str | None = None
    #: Delivery role that must sign when this rule is in play.
    required_role_key: str | None = None


class ApprovalGate(ProvenancedEntity, Blockable):
    """A control point between phases.

    ``blocking=True`` means work genuinely cannot proceed past it. A gate
    extracted from documentation starts non-blocking and must be verified by a
    human before it can stop anything -- otherwise a misread paragraph halts
    delivery, and the platform loses the organization's trust permanently.
    """

    entity_type: EntityType = EntityType.APPROVAL_GATE
    twin: Twin = Twin.DELIVERY

    gate_key: str = Field(min_length=1)
    phase_keys: list[str] = Field(default_factory=list)

    # What must be in place. Each maps to a dimension of computed readiness.
    required_artifact_kinds: list[str] = Field(default_factory=list)
    required_checklist_refs: list[EntityRef] = Field(default_factory=list)
    required_evaluation_refs: list[EntityRef] = Field(default_factory=list)
    required_evidence_refs: list[EntityRef] = Field(default_factory=list)
    required_role_keys: list[str] = Field(
        default_factory=list, description="Delivery roles that must approve."
    )
    rule_refs: list[EntityRef] = Field(default_factory=list)
    policy_refs: list[EntityRef] = Field(default_factory=list)

    allowed_decisions: list[GateDecision] = Field(
        default_factory=lambda: [
            GateDecision.APPROVE,
            GateDecision.REJECT,
            GateDecision.APPROVE_WITH_CONDITIONS,
        ]
    )
    #: Minimum traceability completeness, as a fraction, before the gate is ready.
    minimum_traceability: float = Field(default=0.0, ge=0.0, le=1.0)
    risk_level: RiskClass = RiskClass.MEDIUM

    @model_validator(mode="after")
    def _gate_must_require_something(self) -> ApprovalGate:
        """A gate with no requirements approves everything, which is worse than none.

        It gives the appearance of control while providing none, and it scores
        100% ready on an empty basis.
        """
        if not any(
            (
                self.required_artifact_kinds,
                self.required_checklist_refs,
                self.required_evaluation_refs,
                self.required_evidence_refs,
                self.required_role_keys,
                self.rule_refs,
            )
        ):
            raise ValueError(
                f"gate {self.gate_key!r} requires nothing at all. A gate with no requirements "
                "passes everything while appearing to be a control."
            )
        if GateDecision.APPROVE not in self.allowed_decisions:
            raise ValueError(
                f"gate {self.gate_key!r} does not allow APPROVE; nothing could ever pass it."
            )
        return self


class Approval(MetamodelEntity):
    """A recorded human decision at a gate.

    Instance data, not definition: this is the audit record. It is deliberately
    *not* provenanced -- an approval is not discovered, it is made, and the
    person who made it is named directly.
    """

    entity_type: EntityType = EntityType.APPROVAL
    twin: Twin = Twin.DELIVERY

    id: str = Field(default_factory=new_ulid, min_length=1, max_length=256)
    gate_ref: EntityRef
    subject_ref: EntityRef = Field(description="What was approved -- a change, task or release.")
    decision: GateDecision
    approver: str = Field(min_length=1)
    delivery_role_key: str | None = None
    decided_at: datetime = Field(default_factory=utc_now)
    rationale: str | None = Field(default=None, max_length=8000)
    conditions: list[str] = Field(default_factory=list)
    evidence_refs: list[EntityRef] = Field(default_factory=list)
    #: The computed readiness the approver saw. Recording it means a later
    #: reviewer can tell whether the decision was made on good information.
    readiness_snapshot: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _conditional_approval_needs_conditions(self) -> Approval:
        if self.decision is GateDecision.APPROVE_WITH_CONDITIONS and not self.conditions:
            raise ValueError(
                "APPROVE_WITH_CONDITIONS requires at least one stated condition; otherwise it "
                "is an unconditional approval wearing a hedge."
            )
        if self.decision is GateDecision.REJECT and not self.rationale:
            raise ValueError("a REJECT decision must record a rationale.")
        return self
