"""``foundry/run.py::run_foundry_cycle()`` end to end, over in-memory repos
and the committed golden fixtures under ``tests/fixtures/foundry/``.

Two patterns: ``pattern.pipeline_shape.dbt_model.airflow`` (3 pipelines,
fixtures for all three candidate kinds) and
``pattern.pipeline_shape.airflow_dag.dagster`` (2 pipelines, a fixture for
skill only) -- the second pattern's missing tool/agent fixtures exercise
``on_error="collect"``'s per-item-failure path without aborting the rest
of the run, mirroring ``test_discovery_worked_example_replay.py``'s own
committed-fixture end-to-end style.
"""

from __future__ import annotations

from pathlib import Path

from domain.metamodel.base import EntityRef, ProvenanceState
from domain.metamodel.entities.technical import Pipeline, Project
from domain.metamodel.enums import CandidateStatus, EntityType
from domain.metamodel.registry import MetamodelRegistry
from domain.metamodel.relationships import relationship
from foundry.run import run_foundry_cycle
from foundry.synthesis.replay_client import ReplaySynthesisClient
from persistence.memory import InMemoryGraphRepository, InMemoryMetadataRepository
from project_graph.service import ProjectGraphService

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "foundry"

PROJECT_REF = EntityRef(type=EntityType.PROJECT, id="demo")


def _pipeline(pipeline_id: str, *, kind: str, orchestrator: str, input_asset: str, output_asset: str) -> Pipeline:
    return Pipeline(
        id=pipeline_id,
        name=pipeline_id,
        entity_type=EntityType.PIPELINE,
        project_ref=PROJECT_REF,
        pipeline_kind=kind,
        orchestrator=orchestrator,
        input_refs=[EntityRef(type=EntityType.DATA_ASSET, id=input_asset)],
        output_refs=[EntityRef(type=EntityType.DATA_ASSET, id=output_asset)],
        provenance=ProvenanceState.OBSERVED,
        confidence=1.0,
        discovered_by="test",
    )


def _seed_project(service: ProjectGraphService, registry: MetamodelRegistry) -> None:
    project = Project(
        id="demo",
        name="demo",
        entity_type=EntityType.PROJECT,
        provenance=ProvenanceState.OBSERVED,
        confidence=1.0,
        discovered_by="test",
    )
    service.register_project(project)

    pipelines = [
        _pipeline(f"a{i}", kind="dbt_model", orchestrator="airflow", input_asset="raw_orders", output_asset="stg_orders")
        for i in range(1, 4)
    ] + [
        _pipeline(f"b{i}", kind="airflow_dag", orchestrator="dagster", input_asset="events", output_asset="clean_events")
        for i in range(1, 3)
    ]
    for pipeline in pipelines:
        service.ingest_entity(pipeline)
        service.ingest_relationship(
            relationship("CONTAINS", PROJECT_REF, pipeline.ref(), discovered_by="test"), registry
        )


def test_full_cycle_over_the_committed_fixtures(registry: MetamodelRegistry) -> None:
    metadata = InMemoryMetadataRepository()
    graph = InMemoryGraphRepository()
    service = ProjectGraphService(metadata, graph)
    _seed_project(service, registry)

    client = ReplaySynthesisClient(FIXTURES_DIR)
    report = run_foundry_cycle(service, registry, metadata, graph, PROJECT_REF, client)

    assert len(report.observations) == 5
    assert len(report.patterns) == 2

    # Pattern A has fixtures for all three kinds.
    assert len(report.candidate_skills) == 2  # one per pattern
    assert len(report.candidate_tools) == 1  # pattern A only
    assert len(report.candidate_agents) == 1  # pattern A only

    # Pattern B's missing tool/agent fixtures are recorded, not fatal.
    assert len(report.failed) == 2
    assert all(failure.kind == "synthesis_failed" for failure in report.failed)
    assert any("airflow_dag" in failure.source for failure in report.failed)

    # Every synthesized candidate that got evaluated has a real, passing
    # Evaluation and advanced past CANDIDATE.
    assert len(report.evaluations) == 4  # 2 skills + 1 tool + 1 agent
    assert all(evaluation.passed for evaluation in report.evaluations)
    for candidate in (*report.candidate_skills, *report.candidate_tools, *report.candidate_agents):
        assert candidate.review.candidate_status is CandidateStatus.EVALUATED
        assert candidate.review.evaluation_ref is not None

    # Everything synthesized actually landed in the graph plane through
    # ProjectGraphService -- never a shadow write.
    persisted_skill = metadata.get(EntityType.CANDIDATE_SKILL, report.candidate_skills[0].id)
    assert persisted_skill is not None

    # The pattern with a synthesized candidate is marked as such; both
    # patterns here got at least the skill kind synthesized.
    for pattern in report.patterns:
        assert pattern.synthesized is True


def test_pattern_below_min_frequency_produces_no_candidates(registry: MetamodelRegistry) -> None:
    metadata = InMemoryMetadataRepository()
    graph = InMemoryGraphRepository()
    service = ProjectGraphService(metadata, graph)
    project = Project(
        id="demo", name="demo", entity_type=EntityType.PROJECT,
        provenance=ProvenanceState.OBSERVED, confidence=1.0, discovered_by="test",
    )
    service.register_project(project)
    lone_pipeline = _pipeline("solo", kind="dbt_model", orchestrator="airflow", input_asset="x", output_asset="y")
    service.ingest_entity(lone_pipeline)
    service.ingest_relationship(
        relationship("CONTAINS", PROJECT_REF, lone_pipeline.ref(), discovered_by="test"), registry
    )

    client = ReplaySynthesisClient(FIXTURES_DIR)
    report = run_foundry_cycle(service, registry, metadata, graph, PROJECT_REF, client)

    assert len(report.observations) == 1
    assert report.patterns == []
    assert report.candidate_skills == []
    assert report.failed == []


def test_candidate_kinds_filter_limits_what_gets_synthesized(registry: MetamodelRegistry) -> None:
    metadata = InMemoryMetadataRepository()
    graph = InMemoryGraphRepository()
    service = ProjectGraphService(metadata, graph)
    _seed_project(service, registry)

    client = ReplaySynthesisClient(FIXTURES_DIR)
    report = run_foundry_cycle(
        service, registry, metadata, graph, PROJECT_REF, client, candidate_kinds=("skill",)
    )

    assert len(report.candidate_skills) == 2
    assert report.candidate_tools == []
    assert report.candidate_agents == []
    assert report.failed == []
