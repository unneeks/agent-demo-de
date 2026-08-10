"""Diffing observed capability maturity against a caller-supplied desired
maturity -- the "given a project's capability gaps, resolves which
Engineering Roles are needed" half of the original spec's Composition
Engine line that ADR-0020 deferred.

Pure: takes already-computed `Capability`/`DeliveryCapability` instances
(maturity is `inference.py`'s job, and that needs real project data this
module never touches) and a plain `desired_maturity` mapping. Never
invents a default for `desired_maturity` -- same "no canonical default
anywhere in the registry" reasoning ADR-0019 applied to `ContextPolicy`.
"""

from __future__ import annotations

from datetime import datetime

from domain.metamodel.base import EntityRef, utc_now
from domain.metamodel.entities.shared.capability import Capability, CapabilityGap, DeliveryCapability
from domain.metamodel.enums import EntityType, ProvenanceState
from domain.metamodel.registry import MetamodelRegistry

_DISCOVERED_BY_DEFAULT = "gap-analysis@0.1.0"


def _priority_for(gap_size: int) -> int:
    """1 is highest. A stated, simple rule -- not a scored model."""
    if gap_size >= 3:
        return 1
    if gap_size == 2:
        return 2
    return 3


def _roles_for_capability(capability_key: str, registry: MetamodelRegistry) -> list[str]:
    return sorted(
        role.role_key
        for role in registry.engineering_roles.values()
        if capability_key in role.required_capabilities
    )


def _roles_for_delivery_capability(
    delivery_capability_key: str, registry: MetamodelRegistry
) -> list[str]:
    spec = registry.delivery_capabilities.get(delivery_capability_key)
    return list(spec.realized_by_roles) if spec else []


def analyze_capability_gaps(
    project_ref: EntityRef,
    capabilities: list[Capability],
    delivery_capabilities: list[DeliveryCapability],
    desired_maturity: dict[str, int],
    registry: MetamodelRegistry,
    *,
    discovered_by: str = _DISCOVERED_BY_DEFAULT,
    now: datetime | None = None,
) -> list[CapabilityGap]:
    """A gap for every instance whose `.maturity` is below
    `desired_maturity[key]`. A key in `desired_maturity` with no matching
    instance is simply skipped, not an error -- caller-supplied ambition for
    a capability the project hasn't been observed to have at all yet.

    `provenance=OBSERVED`: this is a deterministic diff of two given
    numbers, transcription rather than inference -- unlike the maturity
    scores themselves, which `inference.py` marks `INFERRED`.
    """
    when = now or utc_now()
    gaps: list[CapabilityGap] = []

    for capability in capabilities:
        desired = desired_maturity.get(capability.capability_key)
        if desired is None or desired <= capability.maturity:
            continue
        gap_size = desired - capability.maturity
        gaps.append(
            CapabilityGap(
                id=f"{project_ref.id}:{capability.capability_key}:gap",
                name=f"{capability.capability_key} capability gap",
                entity_type=EntityType.CAPABILITY_GAP,
                project_ref=project_ref,
                capability_ref=capability.ref(),
                capability_key=capability.capability_key,
                current_maturity=capability.maturity,
                desired_maturity=desired,
                priority=_priority_for(gap_size),
                recommendation=(
                    f"{capability.capability_key} is at maturity {capability.maturity}, "
                    f"desired {desired}."
                ),
                recommended_role_keys=_roles_for_capability(capability.capability_key, registry),
                provenance=ProvenanceState.OBSERVED,
                discovered_by=discovered_by,
                created_at=when,
            )
        )

    for delivery_capability in delivery_capabilities:
        key = delivery_capability.delivery_capability_key
        desired = desired_maturity.get(key)
        if desired is None or desired <= delivery_capability.maturity:
            continue
        gap_size = desired - delivery_capability.maturity
        gaps.append(
            CapabilityGap(
                id=f"{project_ref.id}:{key}:gap",
                name=f"{key} delivery capability gap",
                entity_type=EntityType.CAPABILITY_GAP,
                project_ref=project_ref,
                capability_ref=delivery_capability.ref(),
                capability_key=key,
                current_maturity=delivery_capability.maturity,
                desired_maturity=desired,
                priority=_priority_for(gap_size),
                recommendation=(
                    f"{key} is at maturity {delivery_capability.maturity}, desired {desired}."
                ),
                recommended_role_keys=_roles_for_delivery_capability(key, registry),
                provenance=ProvenanceState.OBSERVED,
                discovered_by=discovered_by,
                created_at=when,
            )
        )

    return gaps


__all__ = ["analyze_capability_gaps"]
