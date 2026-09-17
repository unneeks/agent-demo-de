#!/usr/bin/env python3
"""Record real golden fixtures for the discovery extraction test suite.

Manual, one-time, never invoked by pytest. Requires a live backend
(`ANTHROPIC_API_KEY` by default) and real network access. Wraps whichever
real `ExtractionClient` is selected in a recording proxy and runs the normal
`discover_project` orchestration against the real worked-example project and
the synthetic fixtures for source kinds it doesn't have -- so recording
exercises the exact same walk/prompt/pass logic a real run would, rather
than a parallel reimplementation that could quietly drift from it.

Each file's `(prompt, response_schema, raw_response)` is written to
`tests/fixtures/discovery/golden/<path-slug>.json`, one commit-reviewable
file per input. Regenerating a fixture is a deliberate act with a diff a
reviewer reads -- never a side effect of running tests.

Usage:
    python scripts/record_extraction_fixtures.py                    # Anthropic backend
    python scripts/record_extraction_fixtures.py --backend copilot_cli
    python scripts/record_extraction_fixtures.py --only dbt_demo/models/staging/stg_bank_accounts.sql
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from domain.metamodel.base import utc_now  # noqa: E402
from domain.metamodel.enums import EntityType, ProvenanceState  # noqa: E402
from domain.metamodel.entities.technical import Project  # noqa: E402
from domain.metamodel.registry import MetamodelRegistry  # noqa: E402
from persistence.memory import InMemoryGraphRepository, InMemoryMetadataRepository  # noqa: E402
from project_graph.service import ProjectGraphService  # noqa: E402

from discovery.extraction.client import ExtractionClient  # noqa: E402
from discovery.extraction.replay_client import (  # noqa: E402
    GoldenFixture,
    build_request_hash,
    slug_for_path,
    source_path_from_prompt,
)
from discovery.orchestrate import discover_project  # noqa: E402

WORKED_EXAMPLE_ROOT = REPO_ROOT.parent / "agentic-ai-ollama-demo"
SYNTHETIC_FIXTURES_ROOT = REPO_ROOT / "tests" / "fixtures" / "discovery" / "synthetic"
GOLDEN_FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "discovery" / "golden"


class RecordingExtractionClient:
    """Wraps a real `ExtractionClient`; writes a golden fixture per call.

    A thin proxy, not a reimplementation: every call still goes through the
    real backend exactly as a live run would. Recording is a side effect
    keyed on the same `(prompt, response_schema)` hash `ReplayExtractionClient`
    checks at read time, so a recording made here is guaranteed to satisfy
    the staleness check the moment it's written.
    """

    def __init__(self, inner: ExtractionClient, *, backend_name: str, fixtures_dir: Path) -> None:
        self._inner = inner
        self._backend_name = backend_name
        self._fixtures_dir = fixtures_dir

    def extract(self, *, prompt: str, response_schema: dict[str, Any]) -> dict[str, Any]:
        raw = self._inner.extract(prompt=prompt, response_schema=response_schema)
        source_path = source_path_from_prompt(prompt)
        fixture = GoldenFixture(
            source_path=source_path,
            request_hash=build_request_hash(prompt, response_schema),
            raw_response=raw,
            backend=self._backend_name,
            recorded_at=utc_now().isoformat(),
        )
        self._fixtures_dir.mkdir(parents=True, exist_ok=True)
        fixture_path = self._fixtures_dir / f"{slug_for_path(source_path)}.json"
        fixture_path.write_text(
            json.dumps(fixture.to_json(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"recorded {fixture_path.relative_to(REPO_ROOT)}")
        return raw


def _build_client(backend: str) -> ExtractionClient:
    if backend == "anthropic":
        from discovery.extraction.anthropic_client import AnthropicExtractionClient

        return AnthropicExtractionClient()
    if backend == "copilot_cli":
        from discovery.extraction.copilot_cli_client import CopilotCliExtractionClient

        return CopilotCliExtractionClient()
    raise ValueError(f"unknown backend {backend!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["anthropic", "copilot_cli"], default="anthropic")
    args = parser.parse_args()

    if not WORKED_EXAMPLE_ROOT.is_dir():
        print(f"error: {WORKED_EXAMPLE_ROOT} not found -- this recorder needs the sibling "
              "agentic-ai-ollama-demo/ checkout", file=sys.stderr)
        return 1

    real_client = _build_client(args.backend)
    recording_client = RecordingExtractionClient(
        real_client, backend_name=args.backend, fixtures_dir=GOLDEN_FIXTURES_DIR
    )

    registry = MetamodelRegistry.load()
    project = Project(
        id="agentic-ai-ollama-demo",
        name="agentic-ai-ollama-demo",
        entity_type=EntityType.PROJECT,
        provenance=ProvenanceState.OBSERVED,
        confidence=1.0,
        discovered_by="record_extraction_fixtures@0.1.0",
    )
    service = ProjectGraphService(InMemoryMetadataRepository(), InMemoryGraphRepository())

    report = discover_project(
        service,
        registry,
        project,
        recording_client,
        repository_root=WORKED_EXAMPLE_ROOT,
        repository_id="agentic-ai-ollama-demo",
        on_error="collect",
    )
    print(f"\nworked-example recording: {report.entities_ingested} entities, "
          f"{report.relationships_ingested} relationships, {len(report.skipped)} skipped, "
          f"{len(report.failed)} failed")
    for failure in report.failed:
        print(f"  FAILED: {failure.kind} {failure.source}: {failure.detail}")

    if SYNTHETIC_FIXTURES_ROOT.is_dir() and any(SYNTHETIC_FIXTURES_ROOT.rglob("*")):
        synthetic_project = Project(
            id="synthetic-discovery-fixtures",
            name="synthetic-discovery-fixtures",
            entity_type=EntityType.PROJECT,
            provenance=ProvenanceState.OBSERVED,
            confidence=1.0,
            discovered_by="record_extraction_fixtures@0.1.0",
        )
        synthetic_service = ProjectGraphService(InMemoryMetadataRepository(), InMemoryGraphRepository())
        synthetic_report = discover_project(
            synthetic_service,
            registry,
            synthetic_project,
            recording_client,
            repository_root=SYNTHETIC_FIXTURES_ROOT,
            repository_id="synthetic-discovery-fixtures",
            on_error="collect",
        )
        print(f"\nsynthetic recording: {synthetic_report.entities_ingested} entities, "
              f"{synthetic_report.relationships_ingested} relationships, "
              f"{len(synthetic_report.skipped)} skipped, {len(synthetic_report.failed)} failed")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
