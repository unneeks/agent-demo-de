#!/usr/bin/env python3
"""Run the Web UI dashboard + API Gateway.

Requires the `web` extra (`pip install -e ".[web]"`). Constructs the chosen
backend and calls `webui.create_app()`, then runs it with uvicorn -- a
factory taking constructor arguments is a worse fit for the bare
`uvicorn module:app` CLI form, so this script is the primary way to run it.

`webui/routes/` (the HTML dashboard) is read-only; `/api/*`
(`webui/api/routes/`) is read-write, including `POST /api/projects`. With
the default `--backend memory`, the store starts empty until a caller
registers a project via the API, discovery, the orchestrator, or an agent
run against the same repositories -- or pass `--seed-demo-project` to
hand-build one small project locally for a quick look. Pass
`--agent-fixtures-dir` to make the `POST /api/projects/{id}/agent-runs`
`llm_backend="replay"` option available (see agent_runtime/replay_client.py);
without it, that backend returns a clean 501.

Usage:
    python scripts/run_web.py
    python scripts/run_web.py --seed-demo-project
    python scripts/run_web.py --agent-fixtures-dir tests/fixtures/agent_runtime/golden
    python scripts/run_web.py --backend postgres-neo4j \\
        --postgres-dsn postgresql://... --neo4j-uri bolt://... \\
        --neo4j-user neo4j --neo4j-password ...
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from domain.metamodel.base import EntityRef, ProvenanceState  # noqa: E402
from domain.metamodel.entities.technical import Pipeline, Project  # noqa: E402
from domain.metamodel.enums import EntityType  # noqa: E402
from domain.metamodel.registry import MetamodelRegistry  # noqa: E402
from persistence.memory import InMemoryGraphRepository, InMemoryMetadataRepository  # noqa: E402
from persistence.ports import GraphRepository, MetadataRepository  # noqa: E402
from project_graph.service import ProjectGraphService  # noqa: E402


def _seed_demo_project(service: ProjectGraphService) -> None:
    project = Project(
        id="demo",
        name="Demo Project",
        entity_type=EntityType.PROJECT,
        provenance=ProvenanceState.OBSERVED,
        confidence=1.0,
        discovered_by="run_web@0.1.0",
    )
    service.register_project(project)
    pipeline = Pipeline(
        id="stg_demo",
        name="stg_demo",
        entity_type=EntityType.PIPELINE,
        provenance=ProvenanceState.OBSERVED,
        confidence=1.0,
        discovered_by="run_web@0.1.0",
        project_ref=EntityRef(type=EntityType.PROJECT, id="demo"),
        pipeline_kind="dbt_model",
    )
    service.ingest_entity(pipeline)
    print("seeded demo project 'demo' with one pipeline 'stg_demo'")


def _build_backends(args: argparse.Namespace) -> tuple[MetadataRepository, GraphRepository]:
    if args.backend == "memory":
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--registry-path", default=None, help="Override the registry directory.")
    parser.add_argument("--backend", choices=["memory", "postgres-neo4j"], default="memory")
    parser.add_argument("--postgres-dsn", default=None)
    parser.add_argument("--neo4j-uri", default=None)
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password", default="")
    parser.add_argument(
        "--seed-demo-project",
        action="store_true",
        help="Hand-build one small project so the memory backend shows something.",
    )
    parser.add_argument(
        "--agent-fixtures-dir",
        type=Path,
        default=None,
        help="Directory of recorded agent_runtime session fixtures, enabling "
        "llm_backend='replay' on POST /api/projects/{id}/agent-runs.",
    )
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        print("error: the 'web' extra is not installed -- pip install -e '.[web]'", file=sys.stderr)
        return 1

    registry = MetamodelRegistry.load(args.registry_path)
    metadata, graph = _build_backends(args)
    service = ProjectGraphService(metadata, graph)

    if args.backend == "memory" and args.seed_demo_project:
        _seed_demo_project(service)
    elif args.backend == "memory":
        print(
            "note: in-memory backend starts empty. POST /api/projects to register one, or "
            "load data via discovery/orchestrator/agent runs against these same repositories, "
            "or pass --seed-demo-project for a quick look."
        )
    if args.agent_fixtures_dir is None:
        print("note: no --agent-fixtures-dir given -- llm_backend='replay' will 501 on agent-run requests.")

    from webui.app import create_app

    app = create_app(registry, metadata, graph, agent_fixtures_dir=args.agent_fixtures_dir)
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
