"""Live proof for `CopilotCliExtractionClient`: a real subprocess call
against the same real sibling-project files the golden fixtures were
recorded from.

Skips when neither `copilot` nor `gh copilot` is found on `PATH` -- the
binary-presence analogue of `tests/contract/conftest.py`'s TCP-probe-skip
pattern. Given the larger uncertainty around this backend's
non-interactive/structured-output behavior (see ADR-0013 and
`discovery/extraction/copilot_cli_client.py`'s own docstring), these
assertions are deliberately the most tolerant in the suite: schema-valid
output and at least one successfully ingested entity, proving the adapter's
parsing and failure-handling path works end-to-end against whatever the CLI
actually returns, without over-asserting on behavior nobody has observed yet.
"""

from __future__ import annotations

import shutil

import pytest

from domain.metamodel.entities.technical import Project
from domain.metamodel.enums import EntityType, ProvenanceState
from discovery.orchestrate import discover_project
from persistence.memory import InMemoryGraphRepository, InMemoryMetadataRepository
from project_graph.service import ProjectGraphService

pytestmark = pytest.mark.agent_integration


@pytest.fixture
def copilot_cli_client():
    if not (shutil.which("copilot") or shutil.which("gh")):
        pytest.skip("neither 'copilot' nor 'gh' found on PATH")

    from discovery.extraction.copilot_cli_client import CopilotCliExtractionClient

    return CopilotCliExtractionClient()


def test_live_copilot_cli_extraction_against_the_real_sibling_project(
    sibling_project, registry, copilot_cli_client
) -> None:
    metadata = InMemoryMetadataRepository()
    graph = InMemoryGraphRepository()
    service = ProjectGraphService(metadata, graph)

    project = Project(
        id="ollama-demo-live-copilot",
        name="ollama-demo-live-copilot",
        entity_type=EntityType.PROJECT,
        provenance=ProvenanceState.OBSERVED,
        confidence=1.0,
        discovered_by="test",
    )

    report = discover_project(
        service,
        registry,
        project,
        copilot_cli_client,
        repository_root=sibling_project,
        repository_id="agentic-ai-ollama-demo",
        on_error="collect",
    )

    # Deliberately not asserting specific counts or zero failures: whether
    # the CLI can be driven to return schema-conforming JSON at all for
    # every one of these files is exactly the open question this test
    # exists to observe, not assume. The one thing that must hold is that
    # ingestion never partially wrote a rejected entity/relationship --
    # `report.failed` records every rejection, it doesn't hide one behind a
    # successful count.
    assert report.entities_ingested >= 1, (
        "the Copilot CLI backend produced no ingestable entities at all across "
        "every file in the sibling project -- see report.failed / report.skipped "
        "for what it returned"
    )
    assert report.entities_by_type.get(EntityType.REPOSITORY, 0) == 1
