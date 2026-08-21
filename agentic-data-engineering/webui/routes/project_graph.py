"""GET /projects/{project_id} -- one project's dual-twin graph state.

Reuses `ProjectGraphService.snapshot()`'s exact traversal and relationship-
filter shape, read-only: no `ProjectSnapshot` is built or ingested, nothing
is written. The traversal itself lives in `webui/graph_discovery.py`,
shared with the JSON mirror at `webui/api/routes/reads.py`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates

from domain.metamodel.base import EntityRef
from domain.metamodel.enums import EntityType
from persistence.ports import GraphRepository, MetadataRepository
from project_graph.errors import UnknownProjectError

from webui.context import get_graph, get_metadata, get_templates
from webui.graph_discovery import discover_project_graph

router = APIRouter()


@router.get("/projects/{project_id}")
async def project_graph_view(
    project_id: str,
    request: Request,
    metadata: Annotated[MetadataRepository, Depends(get_metadata)],
    graph: Annotated[GraphRepository, Depends(get_graph)],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
):
    stored_project = metadata.get(EntityType.PROJECT, project_id)
    if stored_project is None:
        raise UnknownProjectError(EntityRef(type=EntityType.PROJECT, id=project_id))

    discovery = discover_project_graph(project_id, metadata, graph)

    return templates.TemplateResponse(
        request,
        "project_graph.html",
        {
            "project_id": project_id,
            "entities_by_type": discovery.entities_by_type,
            "relationships_by_type": discovery.relationships_by_type,
            "catalog_reference_count": discovery.catalog_reference_count,
        },
    )
