"""The reverse of `orchestrator/staffing.py::engineering_roles_for_obligation()`'s
forward walk: given a delivery capability, which `DeliveryTask`s does closing
it actually govern?

    DeliveryCapability.realized_by_roles (registry.delivery_capabilities[key])
      -> EngineeringResponsibility.fulfilled_by_role_keys (reverse scan)
        -> DeliveryRole.responsibility_keys (reverse scan)
          -> DeliveryRole.accountable_for_task_keys

Small catalogs; a linear scan over `registry.responsibilities`/
`.delivery_roles` is the right tool, no new index structure needed.
"""

from __future__ import annotations

from domain.metamodel.registry import LoadedDeliveryModel, MetamodelRegistry


def tasks_governed_by_delivery_capability(
    delivery_capability_key: str,
    registry: MetamodelRegistry,
    delivery_model: LoadedDeliveryModel,
) -> list[str]:
    """DeliveryTask keys that closing this delivery capability's gap would
    actually govern. Empty when the capability, or nothing in its role
    chain, is registered -- a real, reportable outcome, never an error."""
    spec = registry.delivery_capabilities.get(delivery_capability_key)
    if spec is None or not spec.realized_by_roles:
        return []
    realized_by = set(spec.realized_by_roles)

    responsibility_keys = {
        responsibility.responsibility_key
        for responsibility in registry.responsibilities.values()
        if realized_by & set(responsibility.fulfilled_by_role_keys)
    }
    if not responsibility_keys:
        return []

    task_keys: list[str] = []
    seen: set[str] = set()
    for delivery_role in registry.delivery_roles.values():
        if not responsibility_keys & set(delivery_role.responsibility_keys):
            continue
        for task_key in delivery_role.accountable_for_task_keys:
            if task_key not in seen:
                seen.add(task_key)
                task_keys.append(task_key)
    return task_keys


__all__ = ["tasks_governed_by_delivery_capability"]
