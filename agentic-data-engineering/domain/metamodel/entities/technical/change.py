"""Change, Deployment and Incident.

``Change`` is where the two twins meet at runtime. A commit has a technical
blast radius *and* a set of delivery obligations, and the impact engine returns
both. See ``engines/impact/``.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from domain.metamodel.base import (
    EntityRef,
    MetamodelEntity,
    ProvenancedEntity,
    new_ulid,
    utc_now,
)
from domain.metamodel.enums import DeploymentStage, EntityType, RiskClass, Twin


class Change(ProvenancedEntity):
    """A change to the project the platform must reason about."""

    entity_type: EntityType = EntityType.CHANGE
    twin: Twin = Twin.SHARED

    id: str = Field(default_factory=new_ulid, min_length=1, max_length=256)
    project_ref: EntityRef
    change_kind: str = Field(
        description="commit | pull_request | schema_change | deployment | incident | policy_change",
    )
    revision: str | None = None
    base_revision: str | None = None
    author: str | None = None
    title: str | None = None
    changed_paths: list[str] = Field(default_factory=list)
    #: Technical blast radius. Populated by impact analysis, hence provenanced --
    #: an inferred impact is not an observed one.
    impacted_refs: list[EntityRef] = Field(default_factory=list)
    #: Delivery obligations this change triggers: tasks, checklists, gates.
    triggered_task_refs: list[EntityRef] = Field(default_factory=list)
    risk: RiskClass = RiskClass.MEDIUM


class Deployment(MetamodelEntity):
    """A release of something into an environment.

    Two gates enforced here: production requires the evaluation that certified
    it, and every deployment must pin an exact version of what it deployed.
    """

    entity_type: EntityType = EntityType.DEPLOYMENT
    twin: Twin = Twin.TECHNICAL

    id: str = Field(default_factory=new_ulid, min_length=1, max_length=256)
    #: What was deployed -- an Agent, a Pipeline, a release package.
    subject_ref: EntityRef
    project_ref: EntityRef | None = None
    environment: str | None = None
    stage: DeploymentStage = DeploymentStage.CANDIDATE
    deployed_at: datetime = Field(default_factory=utc_now)
    deployed_by: str | None = None
    evaluation_ref: EntityRef | None = None
    #: The gate approval that authorised this. A production deployment with no
    #: approval is exactly the thing the delivery twin exists to catch.
    approval_ref: EntityRef | None = None
    rollback_of: EntityRef | None = None
    active: bool = True

    @model_validator(mode="after")
    def _production_requires_certification(self) -> Deployment:
        if self.stage is DeploymentStage.PRODUCTION:
            if self.evaluation_ref is None:
                raise ValueError(
                    "a production deployment must reference the evaluation that certified it; "
                    "no production deployment without certification."
                )
            if self.approval_ref is None:
                raise ValueError(
                    "a production deployment must reference the gate approval that authorised "
                    "it; an unapproved production release has no audit trail."
                )
        if self.subject_ref.version is None:
            raise ValueError(
                "deployments must pin an exact version, otherwise what was deployed cannot "
                "be reconstructed later."
            )
        return self


class Incident(ProvenancedEntity):
    """A production failure.

    Feeds organizational learning: recurring incident patterns become knowledge
    packs, and a delivery model that keeps producing the same incident has a
    capability gap.
    """

    entity_type: EntityType = EntityType.INCIDENT
    twin: Twin = Twin.SHARED

    id: str = Field(default_factory=new_ulid, min_length=1, max_length=256)
    project_ref: EntityRef
    severity: RiskClass = RiskClass.MEDIUM
    occurred_at: datetime = Field(default_factory=utc_now)
    resolved_at: datetime | None = None
    affected_refs: list[EntityRef] = Field(default_factory=list)
    root_cause: str | None = None
    #: The delivery control that should have caught this, where one is
    #: identifiable. This is how incidents drive delivery model improvement.
    missed_control_ref: EntityRef | None = None
    lessons: list[str] = Field(default_factory=list)
