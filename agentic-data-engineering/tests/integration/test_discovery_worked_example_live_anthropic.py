"""Live proof for `AnthropicExtractionClient`: a real Messages API call
against the same real sibling-project files the golden fixtures were
recorded from.

Skips without `ANTHROPIC_API_KEY` -- the LLM-provider analogue of
`tests/contract/conftest.py`'s TCP-probe-skip precedent. Asserts *structural*
properties only (schema-valid, expected entity types present, counts in a
documented range, zero partial `IngestionError`s), never exact equality to
the golden JSON -- a live call is not expected to reproduce a recording
verbatim, only to produce output shaped the same way (see ADR-0013).
"""

from __future__ import annotations

import os

import pytest

from domain.metamodel.entities.technical import Project
from domain.metamodel.enums import EntityType, ProvenanceState
from discovery.orchestrate import discover_project
from project_graph.service import ProjectGraphService

pytestmark = pytest.mark.agent_integration

#: A live model is non-deterministic in exactly how many entities/edges it
#: reports per file -- these are documented tolerance bands around the
#: golden-fixture counts (`tests/fixtures/discovery/golden/`), not exact
#: expectations. 6 dbt models, 4 seeds, a Dockerfile, docker-compose.yml
#: (4 services) and a README are the fixed input set regardless of what a
#: live call returns for each.
_MIN_PIPELINES = 3  # at least half the 6 real dbt models recognized
_MIN_DATA_ASSETS = 2  # at least half the 4 real seeds recognized


@pytest.fixture
def anthropic_client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")
    try:
        import anthropic  # noqa: F401
    except ImportError:
        pytest.skip("anthropic package not installed (pip install -e '.[agent]')")

    from discovery.extraction.anthropic_client import AnthropicExtractionClient

    return AnthropicExtractionClient()


def test_live_anthropic_extraction_against_the_real_sibling_project(
    sibling_project, registry, anthropic_client
) -> None:
    from persistence.memory import InMemoryGraphRepository, InMemoryMetadataRepository

    metadata = InMemoryMetadataRepository()
    graph = InMemoryGraphRepository()
    service = ProjectGraphService(metadata, graph)

    project = Project(
        id="ollama-demo-live",
        name="ollama-demo-live",
        entity_type=EntityType.PROJECT,
        provenance=ProvenanceState.OBSERVED,
        confidence=1.0,
        discovered_by="test",
    )

    report = discover_project(
        service,
        registry,
        project,
        anthropic_client,
        repository_root=sibling_project,
        repository_id="agentic-ai-ollama-demo",
        on_error="collect",
    )

    assert report.failed == [], f"live extraction produced rejected writes: {report.failed}"
    assert report.entities_by_type.get(EntityType.PIPELINE, 0) >= _MIN_PIPELINES
    assert report.entities_by_type.get(EntityType.DATA_ASSET, 0) >= _MIN_DATA_ASSETS
    assert report.entities_by_type.get(EntityType.REPOSITORY, 0) == 1
    assert report.entities_ingested > 0
    assert report.relationships_ingested > 0
