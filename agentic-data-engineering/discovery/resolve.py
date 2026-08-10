"""Deterministic resolution of relationship candidates against an index of
already-extracted entities.

Bookkeeping over strings the agent already produced -- a
``{(entity_type, id) -> EntityRef}`` dict lookup -- not a second reading of
file content. Stays deterministic for the same reason ``discovery.walk``
does: nothing here interprets a file, it interprets a *symbolic name the
agent already read out of one*.
"""

from __future__ import annotations

from domain.metamodel.base import EntityRef, MetamodelEntity
from domain.metamodel.enums import EntityType, ProvenanceState
from domain.metamodel.relationships import Relationship
from discovery.extraction.parse_response import RelationshipCandidate
from discovery.result import DiscoverySkip

#: Matches `discovery.extraction.parse_response.DISCOVERED_BY` -- one
#: uniform discoverer string for every agent-derived fact, regardless of
#: source kind or which pass produced it.
DISCOVERED_BY = "agent-extraction@0.1.0"


def build_entity_index(entities: list[MetamodelEntity]) -> dict[tuple[EntityType, str], EntityRef]:
    """Index entities by ``(type, id)`` -- the natural key a symbolic name
    resolves against, since the platform assigns `id` from the agent's
    validated `suggested_id` (see `parse_response.py`)."""
    return {(entity.entity_type, entity.id): entity.ref() for entity in entities}


def resolve_relationship_candidates(
    candidates: list[RelationshipCandidate],
    index: dict[tuple[EntityType, str], EntityRef],
) -> tuple[list[Relationship], list[DiscoverySkip]]:
    """Resolve every candidate into a real `Relationship`, or record why it
    couldn't be.

    A candidate that already carries a resolved `target_ref` (a delivery/
    `DESCRIBES` candidate, resolved directly against a known-ids index at
    parse time) passes through unchanged. A technical candidate's
    `target_kind`/`target_symbolic_name` is looked up in `index`; a
    `target_kind` mismatch (the agent said `Pipeline`, the index only has a
    `DataAsset` by that name) is treated as unresolved, never force-matched
    -- the same discipline as an outright missing name.
    """
    resolved: list[Relationship] = []
    skipped: list[DiscoverySkip] = []

    for candidate in candidates:
        if candidate.target_ref is not None:
            target_ref = candidate.target_ref
        else:
            key = (candidate.target_kind, candidate.target_symbolic_name)
            target_ref = index.get(key)
            if target_ref is None:
                target_kind_label = candidate.target_kind.value if candidate.target_kind else "?"
                skipped.append(
                    DiscoverySkip(
                        kind="unresolved_relationship_target",
                        detail=(
                            f"{candidate.type} from {candidate.source_ref} -> "
                            f"{target_kind_label}:{candidate.target_symbolic_name!r} did not "
                            "resolve against any entity discovered this run"
                        ),
                        source=str(candidate.source_ref),
                    )
                )
                continue

        resolved.append(
            Relationship(
                type=candidate.type,
                source=candidate.source_ref,
                target=target_ref,
                provenance=ProvenanceState.INFERRED,
                confidence=candidate.confidence,
                discovered_by=DISCOVERED_BY,
            )
        )

    return resolved, skipped
