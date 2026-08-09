"""POST /api/projects, /api/entities, /api/relationships -- raw metamodel
ingestion, the write path every other write endpoint in this package sits
on top of.

`/api/projects` is a named convenience alias over the generic
`/api/entities`: a `Project` is a real `ENTITY_CLASSES` member and works
through either route -- `register_project()` is itself just `ingest_entity()`
under a friendlier name (project_graph/service.py). Both exist so the
semantic distinction stays visible, not because they do different things.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from pydantic import ValidationError

from domain.metamodel.entities import ENTITY_CLASSES
from domain.metamodel.entities.technical import Project
from domain.metamodel.enums import EntityType
from domain.metamodel.registry import MetamodelRegistry
from domain.metamodel.relationships import Relationship
from persistence.ports import StoredEntity
from project_graph.errors import IngestionError
from project_graph.service import ProjectGraphService

from webui.context import get_registry, get_service

router = APIRouter(prefix="/api")


@router.post("/projects", status_code=status.HTTP_201_CREATED)
async def register_project(
    project: Project,
    service: Annotated[ProjectGraphService, Depends(get_service)],
) -> StoredEntity:
    return service.register_project(project)


@router.post("/entities", status_code=status.HTTP_201_CREATED)
async def ingest_entity(
    body: dict[str, Any],
    service: Annotated[ProjectGraphService, Depends(get_service)],
) -> StoredEntity:
    if "entity_type" not in body:
        raise IngestionError("request body is missing required field 'entity_type'")
    try:
        entity_type = EntityType(body["entity_type"])
    except ValueError as exc:
        raise IngestionError(f"unknown entity_type {body['entity_type']!r}") from exc
    entity_cls = ENTITY_CLASSES[entity_type]
    try:
        entity = entity_cls.model_validate(body)
    except ValidationError as exc:
        raise IngestionError(str(exc)) from exc
    return service.ingest_entity(entity)


@router.post("/relationships", status_code=status.HTTP_201_CREATED)
async def ingest_relationship(
    relationship: Relationship,
    service: Annotated[ProjectGraphService, Depends(get_service)],
    registry: Annotated[MetamodelRegistry, Depends(get_registry)],
) -> Relationship:
    service.ingest_relationship(relationship, registry)
    return relationship
