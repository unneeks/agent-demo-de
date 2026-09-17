"""Gate readiness assessment.

Computes, for one approval gate, how ready the work in front of it actually is:
a score per dimension, an overall status, and an itemized list of what is
blocking. This is the §10 and §26 output, and it is the single most visible
proof that the delivery model is executable rather than documentary.

The engine computes; it does not decide. A ``GateReadiness`` of ``CONDITIONAL``
is information for a human, not an approval. Conflating the two would either let
the platform approve things or reduce it to a checklist nobody trusts.

Decision rule, stated so it is testable:

* any unmet **mandatory** requirement on a **blocking** gate → ``BLOCKED``
* unmet advisory requirements only → ``CONDITIONAL``
* everything met → ``PASS``

A non-blocking gate can never report ``BLOCKED`` -- an advisory gate that halts
delivery is not advisory.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from domain.metamodel.base import EntityRef, MetamodelModel, utc_now
from domain.metamodel.entities.delivery import ApprovalGate
from domain.metamodel.enums import GateDimension, GateStatus
from engines.gates.checklists import ChecklistOutcome


class BlockingItem(MetamodelModel):
    """One thing standing between the work and the gate.

    Always names the control it came from. A blocker a reviewer cannot trace to
    a rule is a blocker they will override.
    """

    dimension: GateDimension
    requirement: str
    detail: str | None = None
    mandatory: bool = True

    def __str__(self) -> str:
        base = f"{self.dimension.value.lower()}: {self.requirement}"
        return f"{base} -- {self.detail}" if self.detail else base


class DimensionScore(MetamodelModel):
    """Readiness in one dimension."""

    dimension: GateDimension
    satisfied: int = Field(ge=0)
    required: int = Field(ge=0)
    score: float = Field(ge=0.0, le=1.0)
    mandatory: bool = True

    @property
    def is_complete(self) -> bool:
        return self.score >= 1.0

    def __str__(self) -> str:
        mark = "OK" if self.is_complete else "--"
        return f"{self.dimension.value.title():14} {self.score:>6.0%} {mark}"


class GateState(MetamodelModel):
    """Everything known about the work presented at a gate.

    Assembled by the caller from the graph and passed in whole, so assessment
    stays a pure function of its inputs and can be replayed exactly.
    """

    #: Artifact kinds actually produced.
    present_artifact_kinds: set[str] = Field(default_factory=set)
    #: Checklist outcomes, keyed by checklist key.
    checklist_outcomes: dict[str, ChecklistOutcome] = Field(default_factory=dict)
    #: Evaluation suite keys that passed.
    passed_evaluations: set[str] = Field(default_factory=set)
    #: Evidence requirement keys that have satisfying evidence.
    satisfied_evidence: set[str] = Field(default_factory=set)
    #: Delivery role keys that have approved.
    approvals: set[str] = Field(default_factory=set)
    #: Traceability completeness, 0..1, from the traceability engine.
    traceability: float = Field(default=1.0, ge=0.0, le=1.0)


class GateReadiness(MetamodelModel):
    """The computed readiness of one gate."""

    gate_key: str
    status: GateStatus
    overall_score: float = Field(ge=0.0, le=1.0)
    dimensions: list[DimensionScore] = Field(default_factory=list)
    blocking_items: list[BlockingItem] = Field(default_factory=list)
    advisory_items: list[BlockingItem] = Field(default_factory=list)
    assessed_at: datetime = Field(default_factory=utc_now)

    @property
    def is_passable(self) -> bool:
        return self.status is not GateStatus.BLOCKED

    def dimension(self, dimension: GateDimension) -> DimensionScore | None:
        return next((d for d in self.dimensions if d.dimension is dimension), None)

    def scores(self) -> dict[str, float]:
        """Flat mapping, for storing on an Approval or a Decision."""
        return {d.dimension.value: d.score for d in self.dimensions}

    def render(self) -> str:
        """The §26 dashboard view, as text."""
        lines = [f"{self.gate_key}"]
        lines += [f"  {d}" for d in self.dimensions]
        lines.append(f"  {'Overall':14} {self.overall_score:>6.0%} -> {self.status.value}")
        if self.blocking_items:
            lines.append("  Blocking:")
            lines += [f"    - {item}" for item in self.blocking_items]
        return "\n".join(lines)


def _score(satisfied: int, required: int) -> float:
    """Score a dimension. A dimension requiring nothing is trivially complete."""
    return 1.0 if required == 0 else satisfied / required


def assess_gate(
    gate: ApprovalGate,
    state: GateState,
    *,
    now: datetime | None = None,
) -> GateReadiness:
    """Assess how ready the work is to pass ``gate``.

    Pure: no I/O, no model call, no clock read unless ``now`` is omitted.
    """
    dimensions: list[DimensionScore] = []
    blocking: list[BlockingItem] = []
    advisory: list[BlockingItem] = []

    # -- artifacts ---------------------------------------------------------
    required_artifacts = list(gate.required_artifact_kinds)
    present = [k for k in required_artifacts if k in state.present_artifact_kinds]
    dimensions.append(
        DimensionScore(
            dimension=GateDimension.ARTIFACTS,
            satisfied=len(present),
            required=len(required_artifacts),
            score=_score(len(present), len(required_artifacts)),
        )
    )
    for kind in required_artifacts:
        if kind not in state.present_artifact_kinds:
            blocking.append(
                BlockingItem(
                    dimension=GateDimension.ARTIFACTS,
                    requirement=kind,
                    detail="required artifact has not been produced",
                )
            )

    # -- checklists --------------------------------------------------------
    required_checklists = [r.id for r in gate.required_checklist_refs]
    complete_checklists = 0
    for key in required_checklists:
        outcome = state.checklist_outcomes.get(key)
        if outcome is None:
            blocking.append(
                BlockingItem(
                    dimension=GateDimension.CHECKLISTS,
                    requirement=key,
                    detail="checklist has not been evaluated",
                )
            )
            continue
        if outcome.complete:
            complete_checklists += 1
            continue
        # An incomplete checklist blocks only for its outstanding *mandatory*
        # items; optional shortfalls are reported but do not stop the gate.
        if outcome.outstanding:
            blocking.append(
                BlockingItem(
                    dimension=GateDimension.CHECKLISTS,
                    requirement=key,
                    detail=f"{len(outcome.outstanding)} mandatory item(s) outstanding: "
                    + ", ".join(outcome.outstanding[:5]),
                )
            )
        else:
            advisory.append(
                BlockingItem(
                    dimension=GateDimension.CHECKLISTS,
                    requirement=key,
                    detail=f"{outcome.completion:.0%} complete, below the declared threshold",
                    mandatory=False,
                )
            )
    dimensions.append(
        DimensionScore(
            dimension=GateDimension.CHECKLISTS,
            satisfied=complete_checklists,
            required=len(required_checklists),
            score=_score(complete_checklists, len(required_checklists)),
        )
    )

    # -- evaluations -------------------------------------------------------
    required_evaluations = [r.id for r in gate.required_evaluation_refs]
    passed = [k for k in required_evaluations if k in state.passed_evaluations]
    dimensions.append(
        DimensionScore(
            dimension=GateDimension.EVALUATIONS,
            satisfied=len(passed),
            required=len(required_evaluations),
            score=_score(len(passed), len(required_evaluations)),
        )
    )
    for key in required_evaluations:
        if key not in state.passed_evaluations:
            blocking.append(
                BlockingItem(
                    dimension=GateDimension.EVALUATIONS,
                    requirement=key,
                    detail="required evaluation has not passed",
                )
            )

    # -- approvals ---------------------------------------------------------
    required_roles = list(gate.required_role_keys)
    approved = [r for r in required_roles if r in state.approvals]
    dimensions.append(
        DimensionScore(
            dimension=GateDimension.APPROVALS,
            satisfied=len(approved),
            required=len(required_roles),
            score=_score(len(approved), len(required_roles)),
        )
    )
    for role_key in required_roles:
        if role_key not in state.approvals:
            blocking.append(
                BlockingItem(
                    dimension=GateDimension.APPROVALS,
                    requirement=role_key,
                    detail="required approval has not been given",
                )
            )

    # -- evidence ----------------------------------------------------------
    required_evidence = [r.id for r in gate.required_evidence_refs]
    satisfied_evidence = [k for k in required_evidence if k in state.satisfied_evidence]
    dimensions.append(
        DimensionScore(
            dimension=GateDimension.EVIDENCE,
            satisfied=len(satisfied_evidence),
            required=len(required_evidence),
            score=_score(len(satisfied_evidence), len(required_evidence)),
        )
    )
    for key in required_evidence:
        if key not in state.satisfied_evidence:
            blocking.append(
                BlockingItem(
                    dimension=GateDimension.EVIDENCE,
                    requirement=key,
                    detail="no evidence satisfies this requirement",
                )
            )

    # -- traceability ------------------------------------------------------
    # Scored against the gate's own minimum rather than against 1.0: most gates
    # accept less than perfect traceability, and holding them all to 100% would
    # make the dimension meaningless.
    traceability_required = gate.minimum_traceability
    dimensions.append(
        DimensionScore(
            dimension=GateDimension.TRACEABILITY,
            satisfied=1 if state.traceability >= traceability_required else 0,
            required=1 if traceability_required > 0 else 0,
            score=state.traceability,
            mandatory=traceability_required > 0,
        )
    )
    if traceability_required > 0 and state.traceability < traceability_required:
        advisory.append(
            BlockingItem(
                dimension=GateDimension.TRACEABILITY,
                requirement="traceability",
                detail=f"{state.traceability:.0%} against a minimum of "
                f"{traceability_required:.0%}",
                mandatory=False,
            )
        )

    # -- overall -----------------------------------------------------------
    # Mean over dimensions that actually require something. Averaging in empty
    # dimensions would let a gate that requires little score the same as one
    # that requires much.
    active = [d for d in dimensions if d.required > 0]
    overall = sum(d.score for d in active) / len(active) if active else 1.0

    if blocking and gate.blocking:
        status = GateStatus.BLOCKED
    elif blocking or advisory:
        # A non-blocking gate with unmet requirements is CONDITIONAL, never
        # BLOCKED -- an advisory gate that halts delivery is not advisory.
        status = GateStatus.CONDITIONAL
    else:
        status = GateStatus.PASS

    return GateReadiness(
        gate_key=gate.gate_key,
        status=status,
        overall_score=min(1.0, max(0.0, overall)),
        dimensions=dimensions,
        blocking_items=blocking,
        advisory_items=advisory,
        assessed_at=now or utc_now(),
    )
