"""``engines/foundry/mining.py``: field-by-field transcription of already-
ingested entities into EngineeringObservations. Pure, no I/O.
"""

from __future__ import annotations

from datetime import datetime, timezone

from domain.metamodel.base import EntityRef
from domain.metamodel.entities.delivery import DeliveryActivity, DeliveryTask
from domain.metamodel.enums import EntityType, ProvenanceState
from domain.metamodel.enums import TestType as _TestType  # avoid pytest's Test*-name collection warning
from engines.foundry.mining import mine_observations

from tests.conftest import make_pipeline, make_test, ref

PROJECT_REF = EntityRef(type=EntityType.PROJECT, id="demo")
NOW = datetime(2026, 8, 10, tzinfo=timezone.utc)


def _delivery_task(task_id: str) -> DeliveryTask:
    return DeliveryTask(
        id=task_id,
        name=task_id,
        entity_type=EntityType.DELIVERY_TASK,
        task_key=task_id,
        input_refs=[ref(EntityType.DELIVERY_INPUT, "in1")],
        output_refs=[ref(EntityType.DELIVERY_OUTPUT, "out1")],
        provenance=ProvenanceState.OBSERVED,
        confidence=1.0,
        discovered_by="test",
    )


def _delivery_activity(activity_id: str) -> DeliveryActivity:
    return DeliveryActivity(
        id=activity_id,
        name=activity_id,
        entity_type=EntityType.DELIVERY_ACTIVITY,
        activity_key=activity_id,
        task_key="task-1",
        sequence=3,
        required_skill_keys=["data-modeling"],
        provenance=ProvenanceState.OBSERVED,
        confidence=1.0,
        discovered_by="test",
    )


class TestMinePipelines:
    def test_transcribes_pipeline_fields(self) -> None:
        pipeline = make_pipeline(
            "p1",
            orchestrator="airflow",
            owners=["data-team"],
            input_refs=[ref(EntityType.DATA_ASSET, "raw_orders")],
            output_refs=[ref(EntityType.DATA_ASSET, "stg_orders")],
        )
        [observation] = mine_observations(PROJECT_REF, pipelines=[pipeline], now=NOW)
        assert observation.source_type == "pipeline"
        assert observation.source_ref == pipeline.ref()
        assert observation.activity == "dbt_model"
        assert observation.technology == "airflow"
        assert observation.actor == "data-team"
        assert observation.inputs == ["raw_orders"]
        assert observation.outputs == ["stg_orders"]
        assert observation.provenance is ProvenanceState.OBSERVED
        assert observation.discovered_at == NOW

    def test_pipeline_with_no_owners_has_no_actor(self) -> None:
        pipeline = make_pipeline("p1", owners=[])
        [observation] = mine_observations(PROJECT_REF, pipelines=[pipeline], now=NOW)
        assert observation.actor is None


class TestMineTests:
    def test_transcribes_test_fields(self) -> None:
        test_entity = make_test(
            "t1",
            test_type=_TestType.SCHEMA,
            framework="pytest",
            covers_refs=[ref(EntityType.DATA_ASSET, "stg_orders")],
            last_result="pass",
        )
        [observation] = mine_observations(PROJECT_REF, tests=[test_entity], now=NOW)
        assert observation.source_type == "test"
        assert observation.activity == str(_TestType.SCHEMA)
        assert observation.technology == "pytest"
        assert observation.inputs == ["stg_orders"]
        assert observation.outcome == "pass"


class TestMineDeliveryTasks:
    def test_transcribes_delivery_task_fields(self) -> None:
        task = _delivery_task("dt1")
        [observation] = mine_observations(PROJECT_REF, delivery_tasks=[task], now=NOW)
        assert observation.source_type == "delivery_task"
        assert observation.activity == "dt1"
        assert observation.inputs == ["in1"]
        assert observation.outputs == ["out1"]
        assert observation.technology is None


class TestMineDeliveryActivities:
    def test_transcribes_delivery_activity_fields(self) -> None:
        activity = _delivery_activity("da1")
        [observation] = mine_observations(PROJECT_REF, delivery_activities=[activity], now=NOW)
        assert observation.source_type == "delivery_activity"
        assert observation.activity == "da1"
        assert observation.sequence == 3
        assert observation.actor == "data-modeling"


class TestMiningOrderAndDeterminism:
    def test_output_order_is_pipelines_then_tests_then_tasks_then_activities(self) -> None:
        observations = mine_observations(
            PROJECT_REF,
            pipelines=[make_pipeline("p1")],
            tests=[make_test("t1")],
            delivery_tasks=[_delivery_task("dt1")],
            delivery_activities=[_delivery_activity("da1")],
            now=NOW,
        )
        assert [o.source_type for o in observations] == [
            "pipeline",
            "test",
            "delivery_task",
            "delivery_activity",
        ]

    def test_two_runs_over_the_same_input_produce_the_same_field_values(self) -> None:
        pipeline = make_pipeline("p1", orchestrator="airflow")
        first = mine_observations(PROJECT_REF, pipelines=[pipeline], now=NOW)
        second = mine_observations(PROJECT_REF, pipelines=[pipeline], now=NOW)
        assert [o.activity for o in first] == [o.activity for o in second]
        assert [o.inputs for o in first] == [o.inputs for o in second]
        assert [o.outputs for o in first] == [o.outputs for o in second]
