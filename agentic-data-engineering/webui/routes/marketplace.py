"""GET /marketplace -- the marketplace catalog (agents/skills/tools/knowledge
packs) plus which agents implement which engineering role, read off the
real `IMPLEMENTED_BY` edges `orchestrator/staffing.py:select_agents()`
writes.

`IMPLEMENTED_BY` is a global catalog fact, not project-scoped, in the graph
plane (ADR-0016) -- the template says so plainly rather than implying a
per-project staffing view this route cannot honestly provide.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates

from domain.metamodel.base import EntityRef
from domain.metamodel.enums import EntityType
from domain.metamodel.registry import MetamodelRegistry
from persistence.ports import GraphRepository

from webui.context import get_graph, get_registry, get_templates

router = APIRouter()


@router.get("/marketplace")
async def marketplace(
    request: Request,
    registry: Annotated[MetamodelRegistry, Depends(get_registry)],
    graph: Annotated[GraphRepository, Depends(get_graph)],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
):
    staffing = []
    for role_key, role in sorted(registry.engineering_roles.items()):
        agent_refs = graph.neighbors(
            EntityRef(type=EntityType.ENGINEERING_ROLE, id=role_key), type_="IMPLEMENTED_BY"
        )
        staffing.append({"role": role, "agent_ids": [ref.id for ref in agent_refs]})

    return templates.TemplateResponse(
        request,
        "marketplace.html",
        {
            "agents": sorted(registry.agents.values(), key=lambda a: a.agent_key),
            "skills": sorted(registry.skills.values(), key=lambda s: s.skill_key),
            "tools": sorted(registry.tools.values(), key=lambda t: t.tool_key),
            "knowledge_packs": sorted(registry.knowledge_packs.values(), key=lambda k: k.knowledge_key),
            "staffing": staffing,
        },
    )
