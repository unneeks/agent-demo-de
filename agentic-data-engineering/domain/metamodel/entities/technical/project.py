"""Project, Repository and CodeArtifact."""

from __future__ import annotations

from pydantic import Field

from domain.metamodel.base import EntityRef, ProvenancedEntity
from domain.metamodel.enums import EntityType, Twin


class Project(ProvenancedEntity):
    """An existing data engineering project the platform has attached to.

    A project has both twins: technical assets *and* a delivery model governing
    how they change. ``delivery_model_ref`` is the join.
    """

    entity_type: EntityType = EntityType.PROJECT
    twin: Twin = Twin.SHARED

    #: Commit SHA (or equivalent) of the snapshot both twins were built from.
    #: This is what makes a recommendation reproducible.
    snapshot_revision: str | None = None
    technologies: list[str] = Field(
        default_factory=list,
        description="Detected technologies as free text; resolved to TechnologyBindings later.",
    )
    owners: list[str] = Field(default_factory=list)
    platform_ref: EntityRef | None = None
    #: The delivery model this project is governed by. Without it the platform
    #: knows what was built but not how the organization is allowed to change it.
    delivery_model_ref: EntityRef | None = None
    business_domain: str | None = None
    criticality: str | None = None


class Repository(ProvenancedEntity):
    """A source repository belonging to a project."""

    entity_type: EntityType = EntityType.REPOSITORY
    twin: Twin = Twin.TECHNICAL

    project_ref: EntityRef
    url: str | None = None
    default_branch: str | None = None
    revision: str | None = None
    languages: list[str] = Field(default_factory=list)


class CodeArtifact(ProvenancedEntity):
    """A file or module of source code.

    Held distinctly from Pipeline because not all code is a pipeline -- helper
    modules, macros and configuration all participate in impact analysis.
    """

    entity_type: EntityType = EntityType.CODE_ARTIFACT
    twin: Twin = Twin.TECHNICAL

    project_ref: EntityRef
    repository_ref: EntityRef | None = None
    path: str = Field(min_length=1)
    language: str | None = None
    content_hash: str | None = None
    lines_of_code: int | None = Field(default=None, ge=0)
    owners: list[str] = Field(default_factory=list)
