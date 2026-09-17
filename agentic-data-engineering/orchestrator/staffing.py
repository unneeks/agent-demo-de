"""SELECT AGENTS: resolving a `DeliveryObligation` to a staffable
`EngineeringRole`, and writing the winning match as a real `IMPLEMENTED_BY`
edge.

Walks the real, already-modeled four-level chain -- the only new code here
is the walk and the write; `resolve_role()` (Phase 4) still decides who
satisfies a role, unchanged and unwrapped:

    DeliveryObligation(kind in {"task","approval"})
      -> DeliveryRole.responsibility_keys
        -> EngineeringResponsibility.fulfilled_by_role_keys
          -> EngineeringRole -> resolve_role(role, registry.agents.values())

`IMPLEMENTED_BY` is written as the global catalog fact the registry's own
description already reads it as ("An engineering role is implemented by an
agent. The role outlives the agent") -- not scoped per project, since
neither `source_types` nor `target_types` names `Project` and
`Relationship.key` is `(source, type, target)` only. The project-specific
record of which obligation triggered a given staffing decision lives in
`StaffingOutcome`/`CycleReport`, and travels with the edge only as
informational `attributes`.
"""

from __future__ import annotations

from collections.abc import Iterable

from domain.metamodel.base import EntityRef
from domain.metamodel.entities.organization import EngineeringRole
from domain.metamodel.enums import EntityType
from domain.metamodel.registry import LoadedDeliveryModel, MetamodelRegistry
from domain.metamodel.relationships import relationship
from engines.composition import resolve_role
from engines.impact import DeliveryObligation
from project_graph.errors import IngestionError
from project_graph.service import ProjectGraphService

from orchestrator.result import StaffingOutcome

#: Only these two DeliveryObligation kinds name a delivery role at all --
#: checklist/gate/evidence/artifact obligations structurally never carry one.
_ROLE_BEARING_KINDS = frozenset({"task", "approval"})

_DISCOVERED_BY = "orchestrator@0.1.0"


def engineering_roles_for_obligation(
    obligation: DeliveryObligation,
    delivery_model: LoadedDeliveryModel,
    registry: MetamodelRegistry,
) -> list[tuple[str, str | None, EngineeringRole | None]]:
    """Walk DeliveryRole -> EngineeringResponsibility -> EngineeringRole for
    one obligation.

    A `"task"` obligation's key is a `DeliveryTask` key; its delivery roles
    come from `task.delivery_role_keys`. A `"approval"` obligation's key is
    already a `DeliveryRole` key (it was built from
    `ApprovalGate.required_role_keys` in `engines.impact`), so it names
    exactly one delivery role, itself.

    A `None` in the last two positions is a real, reportable outcome (an
    unregistered responsibility key, or a responsibility with no
    `fulfilled_by_role_keys` at all -- e.g. `resp.architecture-signoff`),
    never an error and never silently dropped.
    """
    if obligation.kind not in _ROLE_BEARING_KINDS:
        return []

    if obligation.kind == "task":
        task = delivery_model.tasks.get(obligation.key)
        delivery_role_keys = list(task.delivery_role_keys) if task else []
    else:
        delivery_role_keys = [obligation.key]

    results: list[tuple[str, str | None, EngineeringRole | None]] = []
    for delivery_role_key in delivery_role_keys:
        delivery_role = registry.delivery_role(delivery_role_key)
        if delivery_role is None or not delivery_role.responsibility_keys:
            results.append((delivery_role_key, None, None))
            continue
        for responsibility_key in delivery_role.responsibility_keys:
            responsibility = registry.responsibility(responsibility_key)
            if responsibility is None or not responsibility.fulfilled_by_role_keys:
                results.append((delivery_role_key, responsibility_key, None))
                continue
            for role_key in responsibility.fulfilled_by_role_keys:
                role = registry.role(role_key)
                results.append((delivery_role_key, responsibility_key, role))
    return results


def select_agents(
    service: ProjectGraphService,
    registry: MetamodelRegistry,
    delivery_model: LoadedDeliveryModel,
    project_ref: EntityRef,
    obligations: Iterable[DeliveryObligation],
) -> list[StaffingOutcome]:
    """Resolve every task/approval obligation to a staffable EngineeringRole
    and persist the winning match as a real IMPLEMENTED_BY edge.

    `strict_role_match=True` always -- composition's own default and
    IMPLEMENTED_BY's own stated semantics ("an agent is built to implement
    one specific role") -- never widened, so a written staffing decision is
    never a near-miss dressed up as a match. Writes IMPLEMENTED_BY only for
    `resolution.best_match`; near-misses are reported in
    `StaffingOutcome.resolution` for visibility, never persisted as an edge
    that would misrepresent "this agent implements this role."

    A `"task"` obligation's key is a `DeliveryTask` key, so
    `delivery_model.contract_for()` may resolve a real, task-specific
    `DeliveryContract` -- when it does, `resolve_role()` also checks
    delivery conformance, and a role-satisfying agent that cannot
    discharge the contract's mandatory controls is never staffed. An
    `"approval"` obligation's key is a `DeliveryRole` key, not a task key,
    so it never has a contract and keeps today's role-only behaviour.
    """
    outcomes: list[StaffingOutcome] = []

    for obligation in obligations:
        for delivery_role_key, responsibility_key, role in engineering_roles_for_obligation(
            obligation, delivery_model, registry
        ):
            if role is None:
                outcomes.append(
                    StaffingOutcome(
                        obligation_kind=obligation.kind,
                        obligation_key=obligation.key,
                        delivery_role_key=delivery_role_key,
                        responsibility_key=responsibility_key,
                        engineering_role_key=None,
                        resolution=None,
                        staffed_agent_key=None,
                        implemented_by_written=False,
                    )
                )
                continue

            contract = (
                delivery_model.contract_for(obligation.key) if obligation.kind == "task" else None
            )
            resolution = resolve_role(
                role, registry.agents.values(), strict_role_match=True, contract=contract
            )
            staffed_agent_key = resolution.best_match.agent_key if resolution.is_staffable else None
            implemented_by_written = False

            if staffed_agent_key is not None:
                # IMPLEMENTED_BY is a global catalog fact (EngineeringRole ->
                # Agent, no Project in either source_types/target_types), so
                # Relationship.key = (source, type, target) dedupes this to
                # one edge regardless of how many obligations resolve to the
                # same (role, agent) pair -- last write's attributes win.
                agent = registry.agents[staffed_agent_key]
                edge = relationship(
                    "IMPLEMENTED_BY",
                    EntityRef(type=EntityType.ENGINEERING_ROLE, id=role.role_key),
                    agent.ref(),
                    discovered_by=_DISCOVERED_BY,
                    attributes={
                        "project_id": project_ref.id,
                        "obligation_kind": obligation.kind,
                        "obligation_key": obligation.key,
                    },
                )
                try:
                    service.ingest_relationship(edge, registry)
                    implemented_by_written = True
                except IngestionError:
                    implemented_by_written = False

            outcomes.append(
                StaffingOutcome(
                    obligation_kind=obligation.kind,
                    obligation_key=obligation.key,
                    delivery_role_key=delivery_role_key,
                    responsibility_key=responsibility_key,
                    engineering_role_key=role.role_key,
                    resolution=resolution,
                    staffed_agent_key=staffed_agent_key,
                    implemented_by_written=implemented_by_written,
                )
            )

    return outcomes
