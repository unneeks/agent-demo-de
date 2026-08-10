"""DeliveryContract -- the executable binding of a delivery task.

The object agents execute against. It gathers everything a task needs in one
versioned place: inputs, outputs, skills, tools, knowledge, policies, the
checklist that validates the work, the criteria that judge the output, the
evidence that must be produced, and the gate it feeds.

Its most important method is :meth:`conformance_of`, which answers the question
the composition engine must ask and the original design could not:

    Can this agent do the work **according to the organization's delivery model**?

An agent that is technically capable but cannot discharge the mandatory controls
is rejected -- with reasons. That is the difference between a copilot and a
member of a digital engineering organization.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from domain.metamodel.base import EntityRef, MetamodelModel, ProvenancedEntity
from domain.metamodel.enums import EntityType, RiskClass, Twin


class ConformanceGap(MetamodelModel):
    """One reason an agent cannot satisfy a delivery contract."""

    dimension: str = Field(
        description="capability | skill | tool | knowledge | checklist | criterion | gate | artifact"
    )
    missing: str
    mandatory: bool = True
    detail: str | None = None

    def __str__(self) -> str:
        marker = "required" if self.mandatory else "advisory"
        return f"{self.dimension}: {self.missing} ({marker})"


class ContractConformance(MetamodelModel):
    """Whether an agent may execute a contract, and what is missing if not.

    Deliberately not a bare boolean. A rejection nobody can act on is a rejection
    that gets overridden, so the gaps are itemized and split by whether they
    block.
    """

    contract_key: str
    agent_key: str
    technically_capable: bool
    delivery_conformant: bool
    gaps: list[ConformanceGap] = Field(default_factory=list)

    @property
    def is_eligible(self) -> bool:
        """Both dimensions must hold. Technical skill alone is not enough."""
        return self.technically_capable and self.delivery_conformant

    @property
    def blocking_gaps(self) -> list[ConformanceGap]:
        return [gap for gap in self.gaps if gap.mandatory]

    def explain(self) -> str:
        if self.is_eligible:
            return f"{self.agent_key} may execute {self.contract_key}"
        reasons = "; ".join(str(gap) for gap in self.blocking_gaps) or "unspecified"
        return f"{self.agent_key} may not execute {self.contract_key}: {reasons}"


class DeliveryContract(ProvenancedEntity):
    """Everything required to execute one delivery task, bound together."""

    entity_type: EntityType = EntityType.DELIVERY_CONTRACT
    twin: Twin = Twin.DELIVERY

    contract_key: str = Field(min_length=1)
    task_key: str = Field(min_length=1)
    delivery_model_key: str | None = None

    # What the work needs and produces.
    input_refs: list[EntityRef] = Field(default_factory=list)
    output_refs: list[EntityRef] = Field(default_factory=list)
    required_artifact_kinds: list[str] = Field(default_factory=list)

    # What performs it.
    required_capability_keys: list[str] = Field(default_factory=list)
    required_skill_keys: list[str] = Field(default_factory=list)
    required_tool_keys: list[str] = Field(default_factory=list)
    required_knowledge_keys: list[str] = Field(default_factory=list)
    policy_refs: list[EntityRef] = Field(default_factory=list)

    # How it is judged. These are the delivery controls.
    checklist_refs: list[EntityRef] = Field(default_factory=list)
    acceptance_criterion_refs: list[EntityRef] = Field(default_factory=list)
    evidence_requirement_refs: list[EntityRef] = Field(default_factory=list)
    approval_gate_refs: list[EntityRef] = Field(default_factory=list)

    #: Delivery roles accountable for the work under this contract.
    delivery_role_keys: list[str] = Field(default_factory=list)
    risk_level: RiskClass = RiskClass.MEDIUM
    #: Whether an agent may execute this unattended once certified.
    automatable: bool = True

    @model_validator(mode="after")
    def _contract_must_be_judgeable(self) -> DeliveryContract:
        """A contract with no controls cannot be conformed to or failed.

        Agents would 'satisfy' it vacuously, which would let the composition
        engine staff governed work with ungoverned agents.
        """
        if not (self.checklist_refs or self.acceptance_criterion_refs or self.approval_gate_refs):
            raise ValueError(
                f"contract {self.contract_key!r} defines no checklist, acceptance criteria or "
                "approval gate. A contract with no controls cannot be conformed to, so every "
                "agent would satisfy it vacuously."
            )
        return self

    def conformance_of(
        self,
        *,
        agent_key: str,
        capabilities: set[str],
        skills: set[str],
        tools: set[str],
        knowledge: set[str] | None = None,
        supported_checklists: set[str] | None = None,
        supported_gates: set[str] | None = None,
        supported_artifact_kinds: set[str] | None = None,
    ) -> ContractConformance:
        """Assess an agent against both dimensions of this contract.

        Technical capability and delivery conformance are computed separately
        and reported separately, because the interesting failure -- and the one
        the addendum is about -- is an agent that passes the first and fails the
        second.
        """
        knowledge = knowledge or set()
        supported_checklists = supported_checklists or set()
        supported_gates = supported_gates or set()
        supported_artifact_kinds = supported_artifact_kinds or set()

        gaps: list[ConformanceGap] = []

        # -- can it do the work? -------------------------------------------
        for capability in sorted(set(self.required_capability_keys) - capabilities):
            gaps.append(ConformanceGap(dimension="capability", missing=capability))
        for skill in sorted(set(self.required_skill_keys) - skills):
            gaps.append(ConformanceGap(dimension="skill", missing=skill))
        for tool in sorted(set(self.required_tool_keys) - tools):
            gaps.append(ConformanceGap(dimension="tool", missing=tool))
        for pack in sorted(set(self.required_knowledge_keys) - knowledge):
            gaps.append(
                ConformanceGap(dimension="knowledge", missing=pack, mandatory=False)
            )

        technical_dimensions = {"capability", "skill", "tool"}
        technically_capable = not any(
            gap.dimension in technical_dimensions for gap in gaps
        )

        # -- can it do the work the organization's way? --------------------
        delivery_gaps_before = len(gaps)

        for ref in self.checklist_refs:
            if ref.id not in supported_checklists:
                gaps.append(
                    ConformanceGap(
                        dimension="checklist",
                        missing=ref.id,
                        detail="agent does not declare support for this checklist",
                    )
                )
        for ref in self.approval_gate_refs:
            if ref.id not in supported_gates:
                gaps.append(
                    ConformanceGap(
                        dimension="gate",
                        missing=ref.id,
                        detail="agent cannot produce what this gate requires",
                    )
                )
        for kind in sorted(set(self.required_artifact_kinds) - supported_artifact_kinds):
            gaps.append(
                ConformanceGap(
                    dimension="artifact",
                    missing=kind,
                    detail="agent does not produce this artifact kind",
                )
            )

        delivery_conformant = len(gaps) == delivery_gaps_before

        return ContractConformance(
            contract_key=self.contract_key,
            agent_key=agent_key,
            technically_capable=technically_capable,
            delivery_conformant=delivery_conformant,
            gaps=gaps,
        )
