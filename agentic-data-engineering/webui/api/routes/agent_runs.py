"""POST /api/projects/{project_id}/agent-runs -- trigger a real agent run.

`project_id` is accepted for URL/routing symmetry with the other
project-scoped write endpoints, but `run_agents()` itself is not
project-scoped -- stated plainly rather than implying a constraint that
isn't real.

`tool_executor` is never a request field -- `webui.api.translate.
build_agent_run_request()` always hard-codes `SimulatedToolExecutor()`,
matching every prior phase's "all tools simulated" discipline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends

from domain.metamodel.registry import MetamodelRegistry

from orchestrator.agent_step import run_agents
from orchestrator.result import AgentRunOutcome

from webui.api.schemas import AgentRunHttpRequest
from webui.api.translate import build_agent_run_request
from webui.context import get_agent_fixtures_dir, get_registry

router = APIRouter(prefix="/api")


@router.post("/projects/{project_id}/agent-runs")
async def trigger_agent_run(
    project_id: str,
    body: AgentRunHttpRequest,
    registry: Annotated[MetamodelRegistry, Depends(get_registry)],
    agent_fixtures_dir: Annotated[Path | None, Depends(get_agent_fixtures_dir)],
) -> AgentRunOutcome:
    agent_run_request = build_agent_run_request(body, registry, agent_fixtures_dir)
    [outcome] = run_agents(registry, [agent_run_request])
    return outcome
