#!/usr/bin/env python3
"""Interactively walk through onboarding a new project into the platform.

A guided caller of real code paths, not a simulation of them: every step
below is a real `ProjectGraphService`/`discover_project()`/`run_cycle()`
call with a real return value. It composes existing Phase 1-9 functions
exactly the way `orchestrator.run_cycle()` itself does -- "composes;
invents nothing" -- see docs/onboarding.md and ADR-0022.

Discovery is mandatory here: this walkthrough always attempts live
extraction, so it requires either `ANTHROPIC_API_KEY` (`pip install -e
".[agent]"`) or the GitHub Copilot CLI (`copilot`/`gh`) on `PATH`. There is
no offline/skip-discovery mode -- an onboarded project with an empty graph
defeats the point of the walkthrough.

Every prompted value has a matching flag, so the same script also runs
non-interactively:

Usage:
    python scripts/onboard_project.py
    python scripts/onboard_project.py --project-id acme --project-name "Acme Pipelines" \\
        --repository-root ../acme-repo --backend memory
    python scripts/onboard_project.py --backend postgres-neo4j \\
        --postgres-dsn postgresql://ade:devpassword@localhost:5432/ade \\
        --neo4j-uri bolt://localhost:7687 --neo4j-user neo4j --neo4j-password devpassword
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import Literal

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from domain.metamodel.base import EntityRef, ProvenanceState  # noqa: E402
from domain.metamodel.entities.technical import Project  # noqa: E402
from domain.metamodel.enums import EntityType  # noqa: E402
from domain.metamodel.registry import MetamodelRegistry  # noqa: E402
from discovery.extraction.copilot_cli_client import _CANDIDATE_BINARIES  # noqa: E402
from discovery.extraction.errors import ExtractionError  # noqa: E402
from persistence.memory import InMemoryGraphRepository, InMemoryMetadataRepository  # noqa: E402
from persistence.ports import GraphRepository, MetadataRepository  # noqa: E402
from project_graph.service import ProjectGraphService  # noqa: E402
from orchestrator.cycle import ObserveRequest, run_cycle  # noqa: E402
from orchestrator.gap_analysis import GapAnalysisRequest  # noqa: E402
from orchestrator.gate import GateRequest  # noqa: E402

_DISCOVERED_BY = "onboard-project@0.1.0"

_DEFAULT_POSTGRES_DSN = "postgresql://ade:devpassword@localhost:5432/ade"
_DEFAULT_NEO4J_URI = "bolt://localhost:7687"
_DEFAULT_NEO4J_USER = "neo4j"
_DEFAULT_NEO4J_PASSWORD = "devpassword"


# -- pure helpers, unit-testable without mocking input() --------------------


def _parse_str_set(raw: str) -> set[str]:
    return {item.strip() for item in raw.split(",") if item.strip()}


def _project_from_answers(
    *,
    project_id: str,
    name: str,
    technologies: str = "",
    owners: str = "",
    business_domain: str | None = None,
    criticality: str | None = None,
) -> Project:
    return Project(
        id=project_id,
        name=name,
        entity_type=EntityType.PROJECT,
        provenance=ProvenanceState.OBSERVED,
        confidence=1.0,
        discovered_by=_DISCOVERED_BY,
        technologies=sorted(_parse_str_set(technologies)),
        owners=sorted(_parse_str_set(owners)),
        business_domain=business_domain or None,
        criticality=criticality or None,
    )


def _find_extraction_backend(
    has_api_key: bool, copilot_binary: str | None
) -> Literal["anthropic", "copilot"] | None:
    if has_api_key and copilot_binary:
        return None  # caller must ask -- both are available
    if has_api_key:
        return "anthropic"
    if copilot_binary:
        return "copilot"
    return None


# -- interactive I/O ----------------------------------------------------------


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    answer = input(f"{prompt}{suffix}: ").strip()
    return answer or default


def _ask_yes_no(prompt: str, default: bool = False) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    answer = input(f"{prompt} {suffix}: ").strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes")


def _detect_copilot_binary() -> str | None:
    for name in _CANDIDATE_BINARIES:
        if shutil.which(name):
            return name
    return None


def _build_backends(args: argparse.Namespace) -> tuple[MetadataRepository, GraphRepository, str]:
    if args.backend == "memory":
        return InMemoryMetadataRepository(), InMemoryGraphRepository(), "in-memory (state ends when this process exits)"

    from persistence.neo4j.repository import Neo4jGraphRepository, Neo4jUnavailableError
    from persistence.postgres.repository import PostgresMetadataRepository, PostgresUnavailableError

    dsn = args.postgres_dsn or _DEFAULT_POSTGRES_DSN
    neo4j_uri = args.neo4j_uri or _DEFAULT_NEO4J_URI
    try:
        metadata = PostgresMetadataRepository(dsn)
        graph = Neo4jGraphRepository(neo4j_uri, args.neo4j_user, args.neo4j_password)
    except (PostgresUnavailableError, Neo4jUnavailableError) as exc:
        print(f"error: could not reach Postgres/Neo4j ({exc}).", file=sys.stderr)
        print("hint: run `docker compose up -d` first, then retry.", file=sys.stderr)
        raise SystemExit(1)
    return metadata, graph, f"postgres-neo4j ({dsn}, {neo4j_uri})"


def _choose_backend(args: argparse.Namespace) -> tuple[MetadataRepository, GraphRepository, str]:
    if args.backend is not None:
        return _build_backends(args)
    use_real = _ask_yes_no(
        "Use real Postgres+Neo4j (needs `docker compose up -d` first)? "
        "No = in-memory, ephemeral",
        default=False,
    )
    args.backend = "postgres-neo4j" if use_real else "memory"
    return _build_backends(args)


def _choose_delivery_model(registry: MetamodelRegistry, args: argparse.Namespace):
    keys = sorted(registry.delivery_models)
    if not keys:
        print("error: the registry has no loaded DeliveryModel.", file=sys.stderr)
        raise SystemExit(1)
    if args.delivery_model_key:
        chosen = args.delivery_model_key
    elif len(keys) == 1:
        chosen = keys[0]
    else:
        print("Available delivery models:")
        for key in keys:
            print(f"  - {key}")
        chosen = _ask("Delivery model key", default=keys[0])
    loaded = registry.delivery_model(chosen)
    if loaded is None:
        print(f"error: unknown delivery model {chosen!r}.", file=sys.stderr)
        raise SystemExit(1)
    return loaded


def _choose_extraction_client(args: argparse.Namespace):
    has_api_key = bool(args.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY"))
    copilot_binary = _detect_copilot_binary()
    backend = args.extraction_backend or _find_extraction_backend(has_api_key, copilot_binary)

    if backend is None and has_api_key and copilot_binary:
        backend = _ask("Both Anthropic and Copilot CLI are available -- which extraction backend?", default="anthropic")

    if backend is None:
        print(
            "error: discovery needs a live extraction backend, and none is available.\n"
            "  - set ANTHROPIC_API_KEY (pip install -e '.[agent]'), or\n"
            f"  - install the GitHub Copilot CLI ({' or '.join(_CANDIDATE_BINARIES)} on PATH)",
            file=sys.stderr,
        )
        raise SystemExit(1)

    try:
        if backend == "anthropic":
            from discovery.extraction.anthropic_client import AnthropicExtractionClient

            return AnthropicExtractionClient(api_key=args.anthropic_api_key)
        from discovery.extraction.copilot_cli_client import CopilotCliExtractionClient

        return CopilotCliExtractionClient(binary=copilot_binary)
    except ExtractionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)


def _gather_project(args: argparse.Namespace) -> Project:
    project_id = args.project_id or _ask("Project id")
    name = args.project_name or _ask("Project name", default=project_id)
    technologies = args.technologies if args.technologies is not None else _ask("Technologies (comma-separated, optional)")
    owners = args.owners if args.owners is not None else _ask("Owners (comma-separated, optional)")
    business_domain = args.business_domain if args.business_domain is not None else _ask("Business domain (optional)")
    criticality = args.criticality if args.criticality is not None else _ask("Criticality (optional)")
    return _project_from_answers(
        project_id=project_id,
        name=name,
        technologies=technologies,
        owners=owners,
        business_domain=business_domain,
        criticality=criticality,
    )


def _gather_repository(args: argparse.Namespace) -> tuple[Path, str]:
    root_raw = args.repository_root or _ask("Repository root (path to the codebase to scan)")
    root = Path(root_raw).expanduser().resolve()
    if not root.is_dir():
        print(f"error: repository_root {root} does not exist or is not a directory.", file=sys.stderr)
        raise SystemExit(1)
    repository_id = args.repository_id or _ask("Repository id", default=root.name)
    return root, repository_id


def _gather_gap_analysis(registry: MetamodelRegistry, args: argparse.Namespace) -> GapAnalysisRequest | None:
    if args.desired_maturity:
        desired: dict[str, int] = {}
        for pair in args.desired_maturity:
            key, _, value = pair.partition("=")
            desired[key] = int(value)
        return GapAnalysisRequest(desired_maturity=desired)

    if not _ask_yes_no("Run capability gap analysis?", default=False):
        return None

    known = sorted(set(registry.capabilities) | set(registry.delivery_capabilities))
    print("Known capability / delivery-capability keys:")
    for key in known:
        print(f"  - {key}")

    desired = {}
    while True:
        key = _ask("Capability key (blank to finish)")
        if not key:
            break
        if key not in registry.capabilities and key not in registry.delivery_capabilities:
            print(f"  unknown key {key!r}, skipping")
            continue
        level = _ask(f"  desired maturity for {key} (0-5)", default="3")
        desired[key] = int(level)

    return GapAnalysisRequest(desired_maturity=desired) if desired else None


def _gather_gate_request(args: argparse.Namespace) -> GateRequest | None:
    gate_key = args.gate_key
    if gate_key is None:
        gate_key = _ask("Assess a gate now? Enter its key (blank to skip)")
    if not gate_key:
        return None
    present = args.present_artifact_kinds if args.present_artifact_kinds is not None else _ask(
        "  present artifact kinds (comma-separated, optional)"
    )
    evidence = args.satisfied_evidence if args.satisfied_evidence is not None else _ask(
        "  satisfied evidence keys (comma-separated, optional)"
    )
    approvals = args.approvals if args.approvals is not None else _ask(
        "  approval keys already granted (comma-separated, optional)"
    )
    print(
        "  note: checklist_outcomes is left empty here -- per-item ChecklistOutcome "
        "results are richer than a prompt loop should build; use POST "
        "/api/projects/{id}/gates/{key}/assess for that."
    )
    return GateRequest(
        gate_key=gate_key,
        present_artifact_kinds=_parse_str_set(present),
        satisfied_evidence=_parse_str_set(evidence),
        approvals=_parse_str_set(approvals),
    )


def _print_report(report) -> None:
    print("\n=== Cycle report ===")
    if report.discovery is not None:
        d = report.discovery
        print(f"Discovery: {d.entities_ingested} entities, {d.relationships_ingested} relationships ingested")
        for entity_type, count in sorted(d.entities_by_type.items(), key=lambda kv: kv[0].value):
            print(f"  {entity_type.value:20} {count}")
        if d.skipped:
            print(f"  {len(d.skipped)} skipped")
        if d.failed:
            print(f"  {len(d.failed)} failed:")
            for failure in d.failed:
                print(f"    - [{failure.kind}] {failure.source}: {failure.detail}")

    if report.gap_analysis is not None:
        print(f"\nGap analysis: {len(report.gap_analysis.gaps)} gap(s)")
        for gap in report.gap_analysis.gaps:
            print(
                f"  {gap.capability_key}: current={gap.current_maturity} "
                f"desired={gap.desired_maturity} gap={gap.gap_size} priority={gap.priority}"
            )
        for rec in report.gap_analysis.recommendations:
            print(f"  recommend role {rec.role_key} for {rec.capability_key}")

    if report.staffing:
        print(f"\nStaffing: {len(report.staffing)} obligation(s)")
        for outcome in report.staffing:
            staffed = outcome.staffed_agent_key or "-- none staffed --"
            print(f"  {outcome.obligation_key}: {staffed}")

    if report.gate_readiness:
        print("\nGates:")
        for readiness in report.gate_readiness.values():
            print(readiness.render())

    if report.failed:
        print(f"\n{len(report.failed)} cycle step failure(s):")
        for failure in report.failed:
            print(f"  - [{failure.kind}] {failure.source}: {failure.detail}")


def _maybe_launch_dashboard(
    args: argparse.Namespace, registry: MetamodelRegistry, metadata: MetadataRepository, graph: GraphRepository
) -> None:
    if args.backend == "postgres-neo4j":
        dsn = args.postgres_dsn or _DEFAULT_POSTGRES_DSN
        neo4j_uri = args.neo4j_uri or _DEFAULT_NEO4J_URI
        print(
            "\nTo reconnect the dashboard to this data later:\n"
            f"  python scripts/run_web.py --backend postgres-neo4j "
            f"--postgres-dsn {dsn} --neo4j-uri {neo4j_uri} "
            f"--neo4j-user {args.neo4j_user or _DEFAULT_NEO4J_USER}"
        )

    if not _ask_yes_no("\nLaunch the Web UI dashboard now against this data?", default=True):
        return

    try:
        import uvicorn
    except ImportError:
        print("the 'web' extra is not installed -- pip install -e '.[web]'", file=sys.stderr)
        return

    from webui.app import create_app

    app = create_app(registry, metadata, graph, agent_fixtures_dir=None)
    print(f"Serving on http://{args.host}:{args.port} -- Ctrl+C to stop.")
    uvicorn.run(app, host=args.host, port=args.port)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--registry-path", default=None, help="Override the registry directory.")
    parser.add_argument("--delivery-model-key", default=None)

    parser.add_argument("--backend", choices=["memory", "postgres-neo4j"], default=None)
    parser.add_argument("--postgres-dsn", default=None)
    parser.add_argument("--neo4j-uri", default=None)
    parser.add_argument("--neo4j-user", default=None)
    parser.add_argument("--neo4j-password", default=None)

    parser.add_argument("--extraction-backend", choices=["anthropic", "copilot"], default=None)
    parser.add_argument("--anthropic-api-key", default=None)

    parser.add_argument("--project-id", default=None)
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--technologies", default=None)
    parser.add_argument("--owners", default=None)
    parser.add_argument("--business-domain", default=None)
    parser.add_argument("--criticality", default=None)

    parser.add_argument("--repository-root", default=None)
    parser.add_argument("--repository-id", default=None)

    parser.add_argument(
        "--desired-maturity",
        action="append",
        default=None,
        metavar="KEY=LEVEL",
        help="Repeatable. Skips the gap-analysis prompt entirely when given.",
    )

    parser.add_argument("--gate-key", default=None)
    parser.add_argument("--present-artifact-kinds", default=None)
    parser.add_argument("--satisfied-evidence", default=None)
    parser.add_argument("--approvals", default=None)

    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--launch-dashboard", action="store_true", default=None)

    return parser


def main() -> int:
    args = _build_parser().parse_args()

    metadata, graph, backend_description = _choose_backend(args)
    print(f"Backend: {backend_description}")

    registry = MetamodelRegistry.load(args.registry_path)
    delivery_model = _choose_delivery_model(registry, args)
    print(f"Delivery model: {delivery_model.model.model_key}")

    client = _choose_extraction_client(args)

    project = _gather_project(args)
    repository_root, repository_id = _gather_repository(args)
    gap_analysis = _gather_gap_analysis(registry, args)
    gate_request = _gather_gate_request(args)

    service = ProjectGraphService(metadata, graph)
    project_ref = EntityRef(type=EntityType.PROJECT, id=project.id)

    print(f"\nRunning discovery against {repository_root} ...")
    try:
        report = run_cycle(
            service,
            registry,
            delivery_model,
            project_ref,
            metadata,
            observe=ObserveRequest(
                project=project,
                client=client,
                repository_root=repository_root,
                repository_id=repository_id,
                on_error="collect",
            ),
            gap_analysis=gap_analysis,
            gates=[gate_request] if gate_request is not None else None,
            on_error="collect",
        )
    except ExtractionError as exc:
        # A raw extraction-call failure (as opposed to a malformed-response
        # failure `discover_project`'s own on_error="collect" already
        # catches) propagates through `run_cycle` uncaught -- see
        # discovery/extraction/copilot_cli_client.py's own docstring: the
        # Copilot CLI's non-interactive JSON output is unverified. Caught
        # here, at this script's boundary, not inside discover_project/
        # run_cycle, which is out of scope for this walkthrough to change.
        print(f"\nerror: discovery's extraction call failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
    _print_report(report)

    _maybe_launch_dashboard(args, registry, metadata, graph)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
