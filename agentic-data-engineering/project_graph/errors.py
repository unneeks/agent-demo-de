"""Errors raised by the Project Graph service.

Each wraps a lower-level failure (a Pydantic validation error, a registry
rejection, a missing repository row) with the context a caller actually needs:
which project, which operation, which reference. Letting the raw error surface
unadorned is how a stack trace ends up standing in for an error message.
"""

from __future__ import annotations

from domain.metamodel.base import EntityRef


class ProjectGraphError(Exception):
    """Base class for every error this package raises."""


class UnknownProjectError(ProjectGraphError):
    """An operation was attempted against a project that was never registered."""

    def __init__(self, project_ref: EntityRef) -> None:
        self.project_ref = project_ref
        super().__init__(
            f"no project registered at {project_ref}; call register_project() first"
        )


class IngestionError(ProjectGraphError):
    """An entity or relationship failed validation on the way in.

    Wraps the underlying Pydantic or registry error rather than replacing it --
    ``__cause__`` still carries the original -- but adds what the caller of
    ``ingest_entity``/``ingest_relationship`` actually needs to act on: which
    write failed and why, before anything was persisted to either plane.
    """


class SnapshotError(ProjectGraphError):
    """A snapshot could not be taken or restored.

    The honest failure mode when history has been deleted out from under a
    snapshot: a pinned entity or relationship no longer exists in the metadata
    plane. Restoring must fail loudly here, never silently partial-restore --
    a snapshot that quietly reconstructs *some* of what it pinned is worse than
    one that refuses, because it looks trustworthy while being wrong.
    """
