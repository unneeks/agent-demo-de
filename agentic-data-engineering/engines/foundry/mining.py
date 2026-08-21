"""``mine_observations()`` -- deterministic transcription of already-ingested
project-graph entities into ``EngineeringObservation``s.

Pure: no I/O, no ``ProjectGraphService``, no LLM. Reading a field straight
off an already-ingested entity is transcription, not inference
(``provenance=OBSERVED``) -- the same idiom ``discovery/orchestrate.py``'s
structural ``CONTAINS`` edges already use, even though the *source* entity
may itself have been ``INFERRED`` originally.

Scope is deliberately narrow: only ``Pipeline``, ``Test``, ``DeliveryTask``,
``DeliveryActivity`` -- the entity types ``foundry/project_facts.py``
fetches from the project graph. Foundry never re-scans a filesystem or a
document; that is ``discovery/``'s job, and this consumes its output.
"""

from __future__ import annotations

from datetime import datetime

from domain.metamodel.base import EntityRef, utc_now
from domain.metamodel.entities.delivery import DeliveryActivity, DeliveryTask
from domain.metamodel.entities.foundry import EngineeringObservation
from domain.metamodel.entities.technical import Pipeline, Test
from domain.metamodel.enums import ProvenanceState

DISCOVERED_BY = "foundry-mining@0.1.0"


def _from_pipeline(
    pipeline: Pipeline, *, project_ref: EntityRef, discovered_by: str, now: datetime
) -> EngineeringObservation:
    return EngineeringObservation(
        name=f"pipeline observation: {pipeline.id}",
        project_ref=project_ref,
        source_ref=pipeline.ref(),
        source_type="pipeline",
        activity=pipeline.pipeline_kind,
        actor=pipeline.owners[0] if pipeline.owners else None,
        technology=pipeline.orchestrator,
        inputs=[ref.id for ref in pipeline.input_refs],
        outputs=[ref.id for ref in pipeline.output_refs],
        provenance=ProvenanceState.OBSERVED,
        discovered_by=discovered_by,
        discovered_at=now,
    )


def _from_test(
    test: Test, *, project_ref: EntityRef, discovered_by: str, now: datetime
) -> EngineeringObservation:
    return EngineeringObservation(
        name=f"test observation: {test.id}",
        project_ref=project_ref,
        source_ref=test.ref(),
        source_type="test",
        activity=str(test.test_type),
        technology=test.framework,
        inputs=[ref.id for ref in test.covers_refs],
        outcome=test.last_result,
        provenance=ProvenanceState.OBSERVED,
        discovered_by=discovered_by,
        discovered_at=now,
    )


def _from_delivery_task(
    task: DeliveryTask, *, project_ref: EntityRef, discovered_by: str, now: datetime
) -> EngineeringObservation:
    return EngineeringObservation(
        name=f"delivery task observation: {task.id}",
        project_ref=project_ref,
        source_ref=task.ref(),
        source_type="delivery_task",
        activity=task.task_key,
        inputs=[ref.id for ref in task.input_refs],
        outputs=[ref.id for ref in task.output_refs],
        # The delivery twin has no "technology" concept -- left honestly
        # None rather than invented.
        technology=None,
        provenance=ProvenanceState.OBSERVED,
        discovered_by=discovered_by,
        discovered_at=now,
    )


def _from_delivery_activity(
    activity: DeliveryActivity, *, project_ref: EntityRef, discovered_by: str, now: datetime
) -> EngineeringObservation:
    return EngineeringObservation(
        name=f"delivery activity observation: {activity.id}",
        project_ref=project_ref,
        source_ref=activity.ref(),
        source_type="delivery_activity",
        activity=activity.activity_key,
        actor=activity.required_skill_keys[0] if activity.required_skill_keys else None,
        sequence=activity.sequence,
        provenance=ProvenanceState.OBSERVED,
        discovered_by=discovered_by,
        discovered_at=now,
    )


def mine_observations(
    project_ref: EntityRef,
    *,
    pipelines: list[Pipeline] = (),
    tests: list[Test] = (),
    delivery_tasks: list[DeliveryTask] = (),
    delivery_activities: list[DeliveryActivity] = (),
    discovered_by: str = DISCOVERED_BY,
    now: datetime | None = None,
) -> list[EngineeringObservation]:
    """One ``EngineeringObservation`` per source entity, field-by-field
    transcription. Order is deterministic: pipelines, then tests, then
    delivery tasks, then delivery activities, each in input order.
    """
    timestamp = now or utc_now()
    observations: list[EngineeringObservation] = []
    for pipeline in pipelines:
        observations.append(
            _from_pipeline(pipeline, project_ref=project_ref, discovered_by=discovered_by, now=timestamp)
        )
    for test in tests:
        observations.append(
            _from_test(test, project_ref=project_ref, discovered_by=discovered_by, now=timestamp)
        )
    for task in delivery_tasks:
        observations.append(
            _from_delivery_task(task, project_ref=project_ref, discovered_by=discovered_by, now=timestamp)
        )
    for activity in delivery_activities:
        observations.append(
            _from_delivery_activity(
                activity, project_ref=project_ref, discovered_by=discovered_by, now=timestamp
            )
        )
    return observations
