"""Evidence and Finding.

Evidence is what makes the platform's output checkable, and under the addendum
it is also the currency of the delivery model: a gate does not ask "did you do
the work", it asks "show me". ``satisfies_requirement_keys`` is how a piece of
evidence discharges an organizational control.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from domain.metamodel.base import EntityRef, ProvenancedEntity, new_ulid, utc_now
from domain.metamodel.enums import EntityType, RiskClass, Twin


class Evidence(ProvenancedEntity):
    """A citable fact underpinning a decision, finding, evaluation or approval."""

    entity_type: EntityType = EntityType.EVIDENCE
    twin: Twin = Twin.SHARED

    id: str = Field(default_factory=new_ulid, min_length=1, max_length=256)
    evidence_kind: str = Field(
        description="file_excerpt | query_result | test_result | tool_output | "
        "document_section | metric | human_statement | review_record | scan_report",
    )
    #: Where the evidence can be re-read. A citation nobody can follow is not one.
    source_reference: str = Field(min_length=1)
    excerpt: str | None = Field(default=None, max_length=8000)
    content_hash: str | None = None
    collected_at: datetime = Field(default_factory=utc_now)
    subject_ref: EntityRef | None = None
    #: EvidenceRequirement keys this discharges. The join into the delivery model.
    satisfies_requirement_keys: list[str] = Field(default_factory=list)
    retained_until: datetime | None = None


class Finding(ProvenancedEntity):
    """Something the platform concluded and wants a human to see."""

    entity_type: EntityType = EntityType.FINDING
    twin: Twin = Twin.SHARED

    id: str = Field(default_factory=new_ulid, min_length=1, max_length=256)
    project_ref: EntityRef | None = None
    finding_kind: str = Field(
        description="gap | risk | defect | improvement | violation | drift | "
        "delivery_noncompliance",
    )
    statement: str = Field(min_length=1)
    severity: RiskClass = RiskClass.MEDIUM
    recommendation: str | None = None
    subject_refs: list[EntityRef] = Field(default_factory=list)
    #: The delivery control this finding relates to, where there is one.
    control_ref: EntityRef | None = None
    #: Human disposition, fed back into agent scorecards as acceptance rate.
    status: str = Field(default="open", description="open | accepted | rejected | resolved")
    rejected_reason: str | None = None

    @model_validator(mode="after")
    def _findings_must_be_cited(self) -> Finding:
        """No uncited findings, unless a human raised it directly."""
        if not self.evidence_refs and not self.human_verified_by:
            raise ValueError(
                "a Finding must reference at least one Evidence, or name the human who raised "
                "it. Uncited findings are blocked."
            )
        return self
