"""Workflow, Task, Artifact, Event, Decision and Observation.

The execution and audit layer. ``Decision`` is the audit primitive: a concise,
auditable summary plus evidence references and pinned component versions --
never raw chain-of-thought.
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
from domain.metamodel.enums import ApprovalLevel, EntityType, Twin


class Workflow(MetamodelEntity):
    """An ordered set of tasks that agents participate in.

    Binds to *role keys*, never agent ids: if workflows named agents, replacing
    one would rewrite every workflow.
    """

    entity_type: EntityType = EntityType.WORKFLOW
    twin: Twin = Twin.SHARED

    workflow_key: str = Field(min_length=1)
    trigger: str | None = None
    task_refs: list[EntityRef] = Field(default_factory=list)
    participating_role_keys: list[str] = Field(default_factory=list)
    #: Delivery tasks this workflow discharges, tying execution to the process.
    delivery_task_keys: list[str] = Field(default_factory=list)
    inputs: dict[str, str] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)
    policy_refs: list[EntityRef] = Field(default_factory=list)
    max_duration_seconds: int | None = Field(default=None, gt=0)


class Task(MetamodelEntity):
    """A single unit of executed work -- a *run*, not a process definition.

    Distinct from ``DeliveryTask``, which is the organization's template. This is
    one execution of one, and ``delivery_task_key`` links the two.
    """

    entity_type: EntityType = EntityType.TASK
    twin: Twin = Twin.SHARED

    id: str = Field(default_factory=new_ulid, min_length=1, max_length=256)
    workflow_ref: EntityRef | None = None
    agent_ref: EntityRef | None = None
    skill_key: str | None = None
    delivery_task_key: str | None = None
    contract_ref: EntityRef | None = None
    status: str = Field(default="pending", description="pending | running | complete | failed")
    inputs: dict[str, object] = Field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    produced_refs: list[EntityRef] = Field(default_factory=list)
    evidence_refs: list[EntityRef] = Field(default_factory=list)
    error: str | None = None
    #: Idempotency key, so replaying a workflow never duplicates side effects.
    idempotency_key: str | None = None


class Artifact(MetamodelEntity):
    """Something a task run produced.

    Distinct from ``DeliveryArtifact``: this is any output of execution, while a
    DeliveryArtifact is a deliverable the process specifically requires.
    """

    entity_type: EntityType = EntityType.ARTIFACT
    twin: Twin = Twin.SHARED

    id: str = Field(default_factory=new_ulid, min_length=1, max_length=256)
    artifact_kind: str = Field(description="report | patch | test | documentation | diagram")
    produced_by_task_ref: EntityRef | None = None
    content_reference: str = Field(min_length=1)
    content_hash: str | None = None
    media_type: str | None = None


class Event(MetamodelEntity):
    """Something that happened, in the platform or in the observed project."""

    entity_type: EntityType = EntityType.EVENT
    twin: Twin = Twin.SHARED

    id: str = Field(default_factory=new_ulid, min_length=1, max_length=256)
    event_type: str = Field(min_length=1)
    occurred_at: datetime = Field(default_factory=utc_now)
    source: str | None = None
    subject_ref: EntityRef | None = None
    payload: dict[str, object] = Field(default_factory=dict)


class Decision(MetamodelEntity):
    """An auditable record of an agent decision.

    Every field answers a question a reviewer will ask: what was decided, on what
    evidence, under which delivery contract, with which component versions, and
    who approved it.
    """

    entity_type: EntityType = EntityType.DECISION
    twin: Twin = Twin.SHARED

    id: str = Field(default_factory=new_ulid, min_length=1, max_length=256)
    decided_at: datetime = Field(default_factory=utc_now)
    #: Concise and auditable. Explicitly NOT raw chain-of-thought.
    summary: str = Field(min_length=1, max_length=4000)
    outcome: str = Field(min_length=1, description="recommend | approve | reject | escalate | act")
    rationale: str | None = Field(default=None, max_length=8000)

    agent_ref: EntityRef | None = None
    task_ref: EntityRef | None = None
    subject_ref: EntityRef | None = None
    contract_ref: EntityRef | None = None
    evidence_refs: list[EntityRef] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    actions_performed: list[str] = Field(default_factory=list)
    evaluation_refs: list[EntityRef] = Field(default_factory=list)
    #: What was in context when it decided. Without this a decision cannot
    #: honestly be replayed.
    context_bundle_ref: EntityRef | None = None
    #: Gate readiness the agent saw, when the decision concerned a gate.
    gate_readiness: dict[str, float] = Field(default_factory=dict)

    approval_level: ApprovalLevel = ApprovalLevel.NONE
    approved_by: str | None = None
    approved_at: datetime | None = None

    component_versions: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _approval_must_be_attributed(self) -> Decision:
        if self.approval_level is not ApprovalLevel.NONE and not self.approved_by:
            raise ValueError(
                f"decision claims approval_level={self.approval_level.value} but names no "
                "approver; an unattributed approval is not an approval."
            )
        return self


class Observation(ProvenancedEntity):
    """Something noticed at runtime that should update a twin or knowledge.

    Covers both dimensions: a schema drifting is a technical observation, a gate
    that is always waived is a delivery observation, and both should feed back
    into the model rather than being written straight into it.
    """

    entity_type: EntityType = EntityType.OBSERVATION
    twin: Twin = Twin.SHARED

    id: str = Field(default_factory=new_ulid, min_length=1, max_length=256)
    observed_at: datetime = Field(default_factory=utc_now)
    subject_ref: EntityRef
    observation_kind: str = Field(
        description="drift | failure | performance | usage | feedback | correction | "
        "process_deviation | recurring_waiver",
    )
    detail: str | None = None
    metrics: dict[str, float] = Field(default_factory=dict)
    proposes_update_to: list[EntityRef] = Field(default_factory=list)
