#!/usr/bin/env python3
"""Run one Marketplace Foundry cycle against an already-registered project.

Requires the project's graph to already exist -- register it and ingest its
technical/delivery entities first, via discovery, the API, or an agent run.
This script does not observe/discover anything itself; it mines what is
already ingested. Independently invocable at any time, not part of
`orchestrator.cycle.run_cycle()` -- run it again later, on the same
project, to look for new marketplace opportunities as the project evolves.

Usage:
    python scripts/run_foundry.py --project-id demo \\
        --llm-backend replay --synthesis-fixtures-dir tests/fixtures/foundry
    python scripts/run_foundry.py --project-id demo --llm-backend anthropic
    python scripts/run_foundry.py --project-id demo --llm-backend copilot_cli \\
        --backend postgres-neo4j --postgres-dsn postgresql://... \\
        --neo4j-uri bolt://... --neo4j-user neo4j --neo4j-password ...
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from domain.metamodel.base import EntityRef  # noqa: E402
from domain.metamodel.enums import EntityType  # noqa: E402
from domain.metamodel.registry import MetamodelRegistry  # noqa: E402
from discovery.extraction.client import ExtractionClient  # noqa: E402
from foundry.result import FoundryCycleReport  # noqa: E402
from foundry.run import run_foundry_cycle  # noqa: E402
from persistence.ports import GraphRepository, MetadataRepository  # noqa: E402
from project_graph.service import ProjectGraphService  # noqa: E402


def _build_backends(args: argparse.Namespace) -> tuple[MetadataRepository, GraphRepository]:
    if args.backend == "memory":
        from persistence.memory import InMemoryGraphRepository, InMemoryMetadataRepository

        return InMemoryMetadataRepository(), InMemoryGraphRepository()

    from persistence.neo4j.repository import Neo4jGraphRepository
    from persistence.postgres.repository import PostgresMetadataRepository

    if not args.postgres_dsn or not args.neo4j_uri:
        print(
            "error: --backend postgres-neo4j requires --postgres-dsn and --neo4j-uri "
            "(plus --neo4j-user/--neo4j-password)",
            file=sys.stderr,
        )
        raise SystemExit(2)
    metadata = PostgresMetadataRepository(args.postgres_dsn)
    graph = Neo4jGraphRepository(args.neo4j_uri, args.neo4j_user, args.neo4j_password)
    return metadata, graph


def _build_client(args: argparse.Namespace) -> ExtractionClient:
    if args.llm_backend == "replay":
        if args.synthesis_fixtures_dir is None:
            print(
                "error: --llm-backend replay requires --synthesis-fixtures-dir",
                file=sys.stderr,
            )
            raise SystemExit(2)
        from foundry.synthesis.replay_client import ReplaySynthesisClient

        return ReplaySynthesisClient(args.synthesis_fixtures_dir)
    if args.llm_backend == "anthropic":
        from discovery.extraction.anthropic_client import AnthropicExtractionClient

        return AnthropicExtractionClient()
    from discovery.extraction.copilot_cli_client import CopilotCliExtractionClient

    return CopilotCliExtractionClient()


def _print_summary(report: FoundryCycleReport) -> None:
    print(f"project: {report.project_ref}")
    print(f"observations mined: {len(report.observations)}")
    print(f"patterns discovered: {len(report.patterns)}")
    for pattern in report.patterns:
        print(f"  - {pattern.pattern_key} (frequency={pattern.frequency}, similarity={pattern.similarity_score:.2f})")
    print(
        f"candidates synthesized: {len(report.candidate_skills)} skill(s), "
        f"{len(report.candidate_tools)} tool(s), {len(report.candidate_agents)} agent(s)"
    )
    for candidate in (*report.candidate_skills, *report.candidate_tools, *report.candidate_agents):
        print(f"  - {candidate.review.proposed_key}: {candidate.review.candidate_status.value}")
    passed = sum(1 for evaluation in report.evaluations if evaluation.passed)
    print(f"evaluations: {passed}/{len(report.evaluations)} passed")
    if report.failed:
        print(f"failures ({len(report.failed)}):")
        for failure in report.failed:
            print(f"  - [{failure.kind}] {failure.source}: {failure.detail}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project-id", required=True, help="An already-registered project's id.")
    parser.add_argument("--registry-path", default=None, help="Override the registry directory.")
    parser.add_argument("--backend", choices=["memory", "postgres-neo4j"], default="memory")
    parser.add_argument("--postgres-dsn", default=None)
    parser.add_argument("--neo4j-uri", default=None)
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password", default="")
    parser.add_argument(
        "--llm-backend", choices=["replay", "anthropic", "copilot_cli"], default="replay"
    )
    parser.add_argument(
        "--synthesis-fixtures-dir",
        type=Path,
        default=None,
        help="Directory of recorded foundry synthesis fixtures, required for --llm-backend replay.",
    )
    parser.add_argument(
        "--candidate-kinds",
        default="skill,tool,agent",
        help="Comma-separated subset of skill,tool,agent.",
    )
    parser.add_argument("--min-pattern-frequency", type=int, default=2)
    parser.add_argument(
        "--on-error",
        choices=["fail_fast", "collect"],
        default="collect",
    )
    args = parser.parse_args()

    if args.backend == "memory":
        print(
            "note: in-memory backend -- this process must be the same one that already "
            "ingested the project's graph, or that data will not be here to mine."
        )

    registry = MetamodelRegistry.load(args.registry_path)
    metadata, graph = _build_backends(args)
    service = ProjectGraphService(metadata, graph)
    client = _build_client(args)

    project_ref = EntityRef(type=EntityType.PROJECT, id=args.project_id)
    if metadata.get(EntityType.PROJECT, args.project_id) is None:
        print(f"error: no registered project {args.project_id!r} found", file=sys.stderr)
        return 1

    candidate_kinds = tuple(kind.strip() for kind in args.candidate_kinds.split(",") if kind.strip())

    report = run_foundry_cycle(
        service,
        registry,
        metadata,
        graph,
        project_ref,
        client,
        candidate_kinds=candidate_kinds,
        min_pattern_frequency=args.min_pattern_frequency,
        on_error=args.on_error,
    )
    _print_summary(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
