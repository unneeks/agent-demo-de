"""ProjectSnapshot -- the reproducibility primitive.

Acceptance criterion #19 asks that "given the same project snapshot and
component versions, the platform reconstruct why a recommendation was
produced." Before this entity, ``Project.snapshot_revision`` was a field
nothing populated -- a promise with no mechanism behind it.

A snapshot is a computed artifact, not a discovered fact -- the same reasoning
that puts ``ContextBundle`` on ``MetamodelEntity`` rather than
``ProvenancedEntity`` applies here. It pins three things that must all agree for
a past state to be honestly reconstructed:

* which **project version** was current (``project_ref``, version-pinned)
* which **metamodel and registry** were in force (``metamodel_version``,
  inherited from ``Versioned``, plus ``registry_digest``) -- a snapshot can be
  betrayed by data changing under it *or* by the rules changing under it, and
  only the data half is visible if only entity versions are pinned
* exactly which **entities and relationships** existed (``entity_refs``,
  ``relationship_ids``)

Content-hashed the same way ``ContextBundle.bundle_hash`` is computed in
``engines/context/assembler.py`` -- same "sort, then ``json.dumps(sort_keys=True)``
into ``sha256``" shape, for the same reason: two snapshots of identical state,
built by walking entities and edges in different orders, must hash identically.
The actual hashing helper lives in ``project_graph/snapshot.py`` alongside the
service that calls it, consistent with how the context assembler -- not the
``ContextBundle`` entity itself -- owns ``_compute_bundle_hash``.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from domain.metamodel.base import EntityRef, MetamodelEntity, utc_now
from domain.metamodel.enums import EntityType, Twin


class ProjectSnapshot(MetamodelEntity):
    """A pinned, reproducible point-in-time view of one project's twin."""

    entity_type: EntityType = EntityType.PROJECT_SNAPSHOT
    twin: Twin = Twin.SHARED

    #: The project this snapshot captures. Version-pinned -- a snapshot that
    #: cannot name the exact project version it captured is not reproducible.
    project_ref: EntityRef
    #: Hash over the registry's capability, role and relationship-type keys at
    #: capture time, so a snapshot can detect the *rules* changing under it,
    #: not only the data. ``metamodel_version`` for the schema contract itself
    #: is inherited from ``Versioned`` rather than duplicated here.
    registry_digest: str = Field(min_length=1)
    captured_at: datetime = Field(default_factory=utc_now)

    #: Every (type, id, version) triple current for this project at capture
    #: time, as version-pinned refs.
    entity_refs: list[EntityRef] = Field(default_factory=list)
    #: Every relationship id current for this project at capture time.
    relationship_ids: list[str] = Field(default_factory=list)

    #: Digest over registry_digest, entity_refs and relationship_ids, sorted
    #: before hashing so insertion order never affects it.
    snapshot_hash: str = Field(min_length=1)

    def manifest(self) -> dict[str, object]:
        """A compact account of what was captured, for the audit record."""
        return {
            "snapshot_id": self.id,
            "snapshot_hash": self.snapshot_hash,
            "project": str(self.project_ref),
            "metamodel_version": self.metamodel_version,
            "registry_digest": self.registry_digest,
            "captured_at": self.captured_at.isoformat(),
            "entity_count": len(self.entity_refs),
            "relationship_count": len(self.relationship_ids),
        }

    @model_validator(mode="after")
    def _project_ref_must_be_pinned(self) -> ProjectSnapshot:
        if self.project_ref.version is None:
            raise ValueError(
                "project_ref must pin a version -- a snapshot that cannot name the exact "
                "project version it captured is not reproducible."
            )
        for ref in self.entity_refs:
            if ref.version is None:
                raise ValueError(
                    f"entity_refs must all be version-pinned; {ref} is not. An unpinned "
                    "reference in a snapshot defeats the point of taking one."
                )
        return self
