"""Snapshot hashing -- the pure half of the reproducibility primitive.

The entity itself (``ProjectSnapshot``) lives in
``domain.metamodel.entities.shared.snapshot``, alongside every other metamodel
entity. This module holds the computation: given the material a snapshot pins,
produce the digests that make two snapshots of identical state hash identically
regardless of insertion order.

Kept pure and I/O-free on purpose, the same way ``engines/context/assembler.py``
keeps context assembly pure -- ``ProjectGraphService.snapshot()`` does the
repository walking (real I/O) and hands the results here to be hashed and
assembled into a validated ``ProjectSnapshot``.
"""

from __future__ import annotations

import hashlib
import json

from domain.metamodel.base import EntityRef, new_ulid, utc_now
from domain.metamodel.entities.shared.snapshot import ProjectSnapshot
from domain.metamodel.registry import MetamodelRegistry


def compute_registry_digest(registry: MetamodelRegistry) -> str:
    """Digest the registry's rule surface, not its data.

    Covers capability keys (both catalogs), engineering role keys, delivery
    role keys, responsibility keys and relationship type keys -- the
    vocabularies a snapshot's entities and edges were validated against. Two
    registries with the same keys hash identically even if descriptions or
    detection hints differ, because a snapshot cares whether the *rules*
    changed, not whether their prose did.
    """
    payload = {
        "capabilities": sorted(registry.capabilities),
        "delivery_capabilities": sorted(registry.delivery_capabilities),
        "responsibilities": sorted(registry.responsibilities),
        "engineering_roles": sorted(registry.engineering_roles),
        "delivery_roles": sorted(registry.delivery_roles),
        "relationship_types": sorted(registry.relationship_types),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def compute_snapshot_hash(
    registry_digest: str, entity_refs: list[EntityRef], relationship_ids: list[str]
) -> str:
    """Digest over what a snapshot pins, sorted before hashing.

    Mirrors ``engines/context/assembler.py::_compute_bundle_hash``: sort first,
    then ``json.dumps(sort_keys=True)`` into ``sha256``, so the same state
    captured by walking entities or edges in a different order still hashes
    identically.
    """
    payload = {
        "registry_digest": registry_digest,
        "entities": sorted(str(ref) for ref in entity_refs),
        "relationships": sorted(relationship_ids),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_snapshot(
    *,
    project_ref: EntityRef,
    registry: MetamodelRegistry,
    entity_refs: list[EntityRef],
    relationship_ids: list[str],
    snapshot_id: str | None = None,
) -> ProjectSnapshot:
    """Assemble a validated ``ProjectSnapshot`` from already-gathered material.

    The pure counterpart to ``ProjectGraphService.snapshot()``: given what the
    service found by walking the repositories, compute the digests and
    construct the entity. Takes plain data in, so it is testable without any
    persistence adapter at all.
    """
    registry_digest = compute_registry_digest(registry)
    snapshot_hash = compute_snapshot_hash(registry_digest, entity_refs, relationship_ids)
    sorted_entities = sorted(entity_refs, key=str)
    sorted_relationships = sorted(relationship_ids)

    return ProjectSnapshot(
        id=snapshot_id or new_ulid(),
        name=f"snapshot of {project_ref} at {utc_now().isoformat()}",
        entity_type=ProjectSnapshot.model_fields["entity_type"].default,
        project_ref=project_ref,
        registry_digest=registry_digest,
        entity_refs=sorted_entities,
        relationship_ids=sorted_relationships,
        snapshot_hash=snapshot_hash,
    )
