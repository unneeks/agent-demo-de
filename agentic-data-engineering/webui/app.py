"""`create_app()` -- wires the FastAPI app over real backend dependencies.

Three constructor arguments, nothing reaches for an import-time global: the
same dependency-injection discipline `ProjectGraphService(metadata, graph)`
and `run_cycle(service, registry, ...)` already use everywhere else in this
codebase. Every route handler is a thin function calling one or two
existing methods on `ProjectGraphService`/`MetamodelRegistry`/a persistence
port/`orchestrator.gate.assess_gate_readiness()` and rendering the real
returned object -- see docs/web-ui.md.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates

from domain.metamodel.registry import MetamodelRegistry
from orchestrator.errors import UnknownGateError
from persistence.ports import GraphRepository, MetadataRepository
from project_graph.errors import UnknownProjectError
from project_graph.service import ProjectGraphService

from webui.errors import UnknownDeliveryModelError
from webui.routes import delivery_model, evaluations, gate_readiness, marketplace, project_graph, projects

TEMPLATES_DIR = Path(__file__).parent / "templates"


async def _not_found_handler(request: Request, exc: Exception) -> object:
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(
        request, "error.html", {"detail": str(exc)}, status_code=404
    )


def create_app(
    registry: MetamodelRegistry,
    metadata: MetadataRepository,
    graph: GraphRepository,
) -> FastAPI:
    service = ProjectGraphService(metadata, graph)
    app = FastAPI(title="Agentic Data Engineering -- Web UI (read-only)")

    app.state.registry = registry
    app.state.metadata = metadata
    app.state.graph = graph
    app.state.service = service
    app.state.templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    for router in (
        projects.router,
        project_graph.router,
        delivery_model.router,
        marketplace.router,
        evaluations.router,
        gate_readiness.router,
    ):
        app.include_router(router)

    app.add_exception_handler(UnknownProjectError, _not_found_handler)
    app.add_exception_handler(UnknownGateError, _not_found_handler)
    app.add_exception_handler(UnknownDeliveryModelError, _not_found_handler)

    return app


__all__ = ["create_app"]
