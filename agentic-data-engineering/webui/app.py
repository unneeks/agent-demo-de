"""`create_app()` -- wires the FastAPI app over real backend dependencies.

Three required constructor arguments plus one optional one, nothing
reaches for an import-time global: the same dependency-injection
discipline `ProjectGraphService(metadata, graph)` and `run_cycle(service,
registry, ...)` already use everywhere else in this codebase. Every route
handler is a thin function calling one or two existing methods on
`ProjectGraphService`/`MetamodelRegistry`/a persistence port/
`orchestrator`/`agent_runtime` functions and returning the real result --
see docs/web-ui.md and docs/api-gateway.md.

One `FastAPI` instance, two kinds of routes: the six HTML routes
(`webui/routes/`, unchanged in behavior since Phase 8) and the `/api/*`
JSON routes (`webui/api/routes/`, added in Phase 9). `_error_handler`
below is the one place that distinction matters -- FastAPI dispatches
exception handlers by exception *type*, not by path prefix, and the same
exception classes (`UnknownProjectError`, `UnknownGateError`,
`UnknownDeliveryModelError`) can be raised from either kind of route, so
one handler per type branches on `request.url.path` to render `error.html`
for the HTML routes and a JSON envelope for `/api/*`, never the other way
around.
"""

from __future__ import annotations

from functools import partial
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from agent_runtime.errors import AgentRuntimeError
from domain.metamodel.registry import MetamodelRegistry
from orchestrator.errors import UnknownGateError
from orchestrator.workflow import WorkflowRunner, load_workflow_templates
from persistence.ports import GraphRepository, MetadataRepository
from project_graph.errors import IngestionError, UnknownProjectError
from project_graph.service import ProjectGraphService

from webui.api.errors import (
    MissingWorkflowBackendError,
    ReplayBackendUnavailableError,
    UnknownAgentError,
    UnknownWorkflowRunError,
    UnknownWorkflowTemplateError,
)
from webui.api.routes import (
    agent_runs,
    cycles,
    entities,
    evaluations as api_evaluations,
    gates,
    reads,
    workflows as api_workflows,
)
from webui.errors import UnknownDeliveryModelError
from webui.routes import (
    delivery_model,
    evaluations,
    gate_readiness,
    marketplace,
    project_graph,
    projects,
    workflows,
)

TEMPLATES_DIR = Path(__file__).parent / "templates"


async def _error_handler(request: Request, exc: Exception, *, status_code: int) -> Response:
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            {"error": type(exc).__name__, "detail": str(exc), "status_code": status_code},
            status_code=status_code,
        )
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(request, "error.html", {"detail": str(exc)}, status_code=status_code)


def create_app(
    registry: MetamodelRegistry,
    metadata: MetadataRepository,
    graph: GraphRepository,
    *,
    agent_fixtures_dir: Path | None = None,
) -> FastAPI:
    service = ProjectGraphService(metadata, graph)
    app = FastAPI(title="Agentic Data Engineering -- Web UI + API Gateway")

    app.state.registry = registry
    app.state.metadata = metadata
    app.state.graph = graph
    app.state.service = service
    app.state.templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.state.agent_fixtures_dir = agent_fixtures_dir
    try:
        app.state.workflow_templates = load_workflow_templates(registry)
    except FileNotFoundError:
        # Additive feature: a registry root with no workflow_templates.yaml
        # at all (e.g. a minimal registry a test builds for an unrelated
        # fixture) must not break every other route this app serves --
        # only using the workflow dashboard itself fails there, and does
        # so with a real UnknownWorkflowTemplateError naming the empty
        # catalog, not a 500 at startup. A malformed *existing* file
        # (WorkflowTemplateError, bad YAML) is a real bug and is left to
        # raise loudly here instead.
        app.state.workflow_templates = {}
    app.state.workflow_runs: dict[str, WorkflowRunner] = {}

    for router in (
        projects.router,
        project_graph.router,
        delivery_model.router,
        marketplace.router,
        evaluations.router,
        gate_readiness.router,
        workflows.router,
        entities.router,
        reads.router,
        api_evaluations.router,
        gates.router,
        agent_runs.router,
        cycles.router,
        api_workflows.router,
    ):
        app.include_router(router)

    for exc_type, status_code in (
        (UnknownProjectError, 404),
        (UnknownGateError, 404),
        (UnknownDeliveryModelError, 404),
        (UnknownAgentError, 404),
        (UnknownWorkflowTemplateError, 404),
        (UnknownWorkflowRunError, 404),
        (MissingWorkflowBackendError, 422),
        (ReplayBackendUnavailableError, 501),
        (IngestionError, 422),
        (ValueError, 422),
        (AgentRuntimeError, 502),
        # Defensive fallback: an unknown suite_key/agent_key that reaches all
        # the way to a raw registry.evaluation_suites[...]/.agents[...]
        # lookup (i.e. one translate.py's own named checks didn't already
        # catch) must still 404 cleanly, never surface as an unhandled 500.
        (KeyError, 404),
    ):
        app.add_exception_handler(exc_type, partial(_error_handler, status_code=status_code))

    return app


__all__ = ["create_app"]
