"""GET / -- the registered-projects list.

Deliberately does not traverse the graph per project to show entity
counts: that would be O(projects x traversal) on an index page. Named as a
real scaling limitation in docs/web-ui.md's "what this is not", not
silently worked around.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates

from domain.metamodel.entities.technical import Project
from domain.metamodel.enums import EntityType
from persistence.ports import MetadataRepository

from webui.context import get_metadata, get_templates

router = APIRouter()


@router.get("/")
async def list_projects(
    request: Request,
    metadata: Annotated[MetadataRepository, Depends(get_metadata)],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
):
    stored = metadata.list(EntityType.PROJECT)
    projects = sorted(
        (Project.model_validate(row.payload) for row in stored),
        key=lambda p: p.id,
    )
    return templates.TemplateResponse(request, "projects.html", {"projects": projects})
