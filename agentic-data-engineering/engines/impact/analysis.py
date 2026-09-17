"""Dual impact analysis: technical blast radius plus delivery obligations.

The addendum's §20. A change to ``customer_address.sql`` has two consequences
that must be reported together:

* **Technical** -- which pipelines, assets, tests and consumers are affected.
* **Delivery** -- which tasks are now owed, which checklists apply, which gates
  need re-approval, what evidence must be produced and who must sign.

Reporting only the first is what a good static-analysis tool does. Reporting
both is what a member of an engineering organization does, and it is only
possible because the two twins share one graph.

Pure: it takes a graph and a change, and returns a result. No I/O, no model.
"""

from __future__ import annotations

from pydantic import Field

from domain.metamodel.base import EntityRef, MetamodelModel
from domain.metamodel.entities.technical.change import Change
from domain.metamodel.enums import EntityType, RiskClass
from domain.metamodel.registry import LoadedDeliveryModel
from persistence.ports import GraphRepository, TraversalResult

#: Edges followed when computing the technical blast radius.
TECHNICAL_EDGES = ("DEPENDS_ON", "CONTAINS", "COVERS", "HAS_SCHEMA", "IMPLEMENTS")

#: Edges followed from an impacted technical entity into the delivery model.
DELIVERY_EDGES = ("GOVERNS", "DESCRIBES")


class TechnicalImpact(MetamodelModel):
    """What the change touches in the technical twin."""

    impacted: list[TraversalResult] = Field(default_factory=list)
    #: Tests covering anything impacted -- the selection a regression agent runs.
    selected_tests: list[EntityRef] = Field(default_factory=list)

    def refs(self) -> list[EntityRef]:
        return [r.ref for r in self.impacted]

    def of_type(self, entity_type: EntityType) -> list[TraversalResult]:
        return [r for r in self.impacted if r.ref.type is entity_type]

    @property
    def max_confidence(self) -> float:
        return max((r.confidence for r in self.impacted), default=0.0)


class DeliveryObligation(MetamodelModel):
    """One thing the delivery model now requires because of this change."""

    kind: str = Field(description="task | checklist | gate | evidence | approval | artifact")
    key: str
    reason: str
    #: Confidence inherited from the graph path that produced it. A task reached
    #: only through an inferred DESCRIBES edge is a weaker claim than one reached
    #: through an observed GOVERNS edge, and a reviewer should see the difference.
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    mandatory: bool = True


class DeliveryImpact(MetamodelModel):
    """What the organization's process now requires."""

    triggered_tasks: list[DeliveryObligation] = Field(default_factory=list)
    required_checklists: list[DeliveryObligation] = Field(default_factory=list)
    gates_to_clear: list[DeliveryObligation] = Field(default_factory=list)
    evidence_required: list[DeliveryObligation] = Field(default_factory=list)
    required_approvers: list[DeliveryObligation] = Field(default_factory=list)
    documentation_to_update: list[DeliveryObligation] = Field(default_factory=list)

    def all_obligations(self) -> list[DeliveryObligation]:
        return [
            *self.triggered_tasks,
            *self.required_checklists,
            *self.gates_to_clear,
            *self.evidence_required,
            *self.required_approvers,
            *self.documentation_to_update,
        ]

    @property
    def is_empty(self) -> bool:
        return not self.all_obligations()


class ChangeImpact(MetamodelModel):
    """Both dimensions of a change's consequences."""

    change_id: str
    technical: TechnicalImpact
    delivery: DeliveryImpact
    risk: RiskClass = RiskClass.MEDIUM

    def render(self) -> str:
        lines = [f"Change {self.change_id} (risk {self.risk.value})", "  Technical impact:"]
        lines += [
            f"    {r.ref} (confidence {r.confidence:.2f}, depth {r.depth})"
            for r in self.technical.impacted
        ] or ["    none"]
        lines.append("  Delivery impact:")
        obligations = self.delivery.all_obligations()
        lines += [
            f"    [{o.kind}] {o.key} -- {o.reason}"
            + (f" (confidence {o.confidence:.2f})" if o.confidence < 1.0 else "")
            for o in obligations
        ] or ["    none"]
        return "\n".join(lines)


def analyze_technical_impact(
    change: Change,
    graph: GraphRepository,
    *,
    seeds: list[EntityRef] | None = None,
    max_depth: int = 5,
    min_confidence: float = 0.0,
) -> TechnicalImpact:
    """Walk the technical twin outward from what the change touched.

    Walks *incoming* edges: the question is what depends on the changed thing,
    not what it depends on. When a node is reachable by several paths the most
    confident wins, and confidence degrades multiplicatively along inferred hops.
    """
    starting_points = seeds if seeds is not None else list(change.impacted_refs)
    best: dict[str, TraversalResult] = {}

    for seed in starting_points:
        # The seed is itself impacted -- it is the thing that changed.
        key = str(seed.identity)
        if key not in best:
            best[key] = TraversalResult(ref=seed.identity, depth=0, confidence=1.0, path=[])
        for result in graph.traverse(
            seed,
            relationship_types=list(TECHNICAL_EDGES),
            max_depth=max_depth,
            min_confidence=min_confidence,
            direction="incoming",
        ):
            existing = best.get(str(result.ref))
            if existing is None or result.confidence > existing.confidence:
                best[str(result.ref)] = result

    impacted = sorted(best.values(), key=lambda r: (-r.confidence, r.depth, str(r.ref)))
    return TechnicalImpact(
        impacted=impacted,
        selected_tests=[r.ref for r in impacted if r.ref.type is EntityType.TEST],
    )


def analyze_delivery_impact(
    technical: TechnicalImpact,
    graph: GraphRepository,
    model: LoadedDeliveryModel,
    *,
    min_confidence: float = 0.0,
) -> DeliveryImpact:
    """Resolve what the delivery model owes, given a technical blast radius.

    Crosses from the technical twin into the delivery twin through ``GOVERNS``
    and ``DESCRIBES``, then expands each triggered task into its checklists,
    gates, evidence requirements and accountable roles.
    """
    impact = DeliveryImpact()
    seen_tasks: dict[str, float] = {}
    documentation: dict[str, float] = {}

    for result in technical.impacted:
        for rel in graph.relationships(target=result.ref):
            if rel.type not in DELIVERY_EDGES:
                continue
            # Confidence compounds: a task reached through an inferred edge from
            # an inferred impact is doubly uncertain, and must read that way.
            hop = 1.0 if rel.confidence is None else rel.confidence
            confidence = result.confidence * hop
            if confidence < min_confidence:
                continue

            if rel.type == "GOVERNS" and rel.source.type is EntityType.DELIVERY_TASK:
                key = rel.source.id
                seen_tasks[key] = max(seen_tasks.get(key, 0.0), confidence)
            elif rel.type == "DESCRIBES" and rel.source.type is EntityType.DELIVERY_ARTIFACT:
                key = rel.source.id
                documentation[key] = max(documentation.get(key, 0.0), confidence)

    for artifact_key, confidence in sorted(documentation.items()):
        impact.documentation_to_update.append(
            DeliveryObligation(
                kind="artifact",
                key=artifact_key,
                reason="documents a changed technical entity and may now be out of date",
                confidence=confidence,
                mandatory=False,
            )
        )

    approvers: dict[str, float] = {}
    for task_key, confidence in sorted(seen_tasks.items()):
        task = model.tasks.get(task_key)
        if task is None:
            continue
        impact.triggered_tasks.append(
            DeliveryObligation(
                kind="task",
                key=task_key,
                reason="governs a changed technical entity",
                confidence=confidence,
            )
        )
        for ref in task.checklist_refs:
            impact.required_checklists.append(
                DeliveryObligation(
                    kind="checklist",
                    key=ref.id,
                    reason=f"required by {task_key}",
                    confidence=confidence,
                )
            )
        for ref in task.approval_gate_refs:
            impact.gates_to_clear.append(
                DeliveryObligation(
                    kind="gate",
                    key=ref.id,
                    reason=f"{task_key} ends at this gate",
                    confidence=confidence,
                )
            )
            gate = model.gates.get(ref.id)
            if gate is not None:
                for role_key in gate.required_role_keys:
                    approvers[role_key] = max(approvers.get(role_key, 0.0), confidence)
        for ref in task.evidence_requirement_refs:
            requirement = model.evidence_requirements.get(ref.id)
            impact.evidence_required.append(
                DeliveryObligation(
                    kind="evidence",
                    key=ref.id,
                    reason=f"required by {task_key}",
                    confidence=confidence,
                    mandatory=requirement.mandatory if requirement else True,
                )
            )

    for role_key, confidence in sorted(approvers.items()):
        impact.required_approvers.append(
            DeliveryObligation(
                kind="approval",
                key=role_key,
                reason="must approve a gate this change must clear",
                confidence=confidence,
            )
        )

    return impact


def analyze_impact(
    change: Change,
    graph: GraphRepository,
    model: LoadedDeliveryModel,
    *,
    seeds: list[EntityRef] | None = None,
    max_depth: int = 5,
    min_confidence: float = 0.0,
) -> ChangeImpact:
    """Both dimensions in one call. The §20 output.

    Risk is escalated by delivery obligations, not only by technical reach: a
    one-line change that trips a security gate is a higher-risk change than a
    large one that trips nothing, and the delivery twin is the only thing that
    knows it.
    """
    technical = analyze_technical_impact(
        change, graph, seeds=seeds, max_depth=max_depth, min_confidence=min_confidence
    )
    delivery = analyze_delivery_impact(technical, graph, model, min_confidence=min_confidence)

    risk = change.risk
    gate_risks = [
        model.gates[o.key].risk_level for o in delivery.gates_to_clear if o.key in model.gates
    ]
    if gate_risks:
        order = [RiskClass.LOW, RiskClass.MEDIUM, RiskClass.HIGH, RiskClass.CRITICAL]
        highest = max(gate_risks, key=order.index)
        if order.index(highest) > order.index(risk):
            risk = highest

    return ChangeImpact(
        change_id=change.id, technical=technical, delivery=delivery, risk=risk
    )
