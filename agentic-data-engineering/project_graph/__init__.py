"""The Project Graph service -- lifecycle, snapshotting, and query facade for
one project's dual digital twin.

A thin front door over ``persistence.ports`` and ``engines.*``, not a fourth
persistence layer: every write still goes through ``MetadataRepository``/
``GraphRepository``, every read still returns Phase 1 entities and Phase 1
engine result types unchanged.
"""

from project_graph.errors import (
    IngestionError,
    ProjectGraphError,
    SnapshotError,
    UnknownProjectError,
)
from project_graph.service import ProjectGraphService
from project_graph.snapshot import (
    build_snapshot,
    compute_registry_digest,
    compute_snapshot_hash,
)

__all__ = [
    "IngestionError",
    "ProjectGraphError",
    "ProjectGraphService",
    "SnapshotError",
    "UnknownProjectError",
    "build_snapshot",
    "compute_registry_digest",
    "compute_snapshot_hash",
]
