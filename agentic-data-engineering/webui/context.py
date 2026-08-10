"""Dependency accessors -- the one place `request.app.state` is read.

Every route depends on these via FastAPI's `Depends()` rather than reaching
into `request.app.state` itself, keeping that one indirection confined to
this file. `request.app.state` belongs to the specific `FastAPI` instance
`create_app()` returned, not a module-level global, so two apps built by
two calls to `create_app()` never share state -- the same in-process,
no-global discipline every other module in this codebase already follows
(`ProjectGraphService(metadata, graph)`, `run_cycle(service, registry, ...)`).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from domain.metamodel.registry import MetamodelRegistry
from persistence.ports import GraphRepository, MetadataRepository
from project_graph.service import ProjectGraphService


def get_registry(request: Request) -> MetamodelRegistry:
    return request.app.state.registry


def get_metadata(request: Request) -> MetadataRepository:
    return request.app.state.metadata


def get_graph(request: Request) -> GraphRepository:
    return request.app.state.graph


def get_service(request: Request) -> ProjectGraphService:
    return request.app.state.service


def get_templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates


def get_agent_fixtures_dir(request: Request) -> Path | None:
    return request.app.state.agent_fixtures_dir
