"""Delivery Twin: how the organization builds and governs change.

Delivery documentation modelled as structured, versioned, executable metadata
rather than as reference material an LLM reads. Every entity here is something
the platform can compute against -- a checklist it can evaluate, a gate whose
readiness it can calculate, a contract it can hold an agent to.
"""

from domain.metamodel.entities.delivery.checklists import (
    AcceptanceCriterion,
    Checklist,
    ChecklistItem,
    ChecklistItemResult,
    DefinitionOfDone,
    Waiver,
)
from domain.metamodel.entities.delivery.contracts import (
    ConformanceGap,
    ContractConformance,
    DeliveryContract,
)
from domain.metamodel.entities.delivery.gates import (
    Approval,
    ApprovalGate,
    ApprovalRule,
    EvidenceRequirement,
)
from domain.metamodel.entities.delivery.model import (
    DeliveryModel,
    DeliveryPhase,
    DeliveryProcess,
)
from domain.metamodel.entities.delivery.standards import (
    Control,
    DeliveryArtifact,
    Methodology,
    RaciAssignment,
    Standard,
    Template,
)
from domain.metamodel.entities.delivery.tasks import (
    DeliveryActivity,
    DeliveryInput,
    DeliveryOutput,
    DeliveryTask,
)

__all__ = [
    "AcceptanceCriterion",
    "Approval",
    "ApprovalGate",
    "ApprovalRule",
    "Checklist",
    "ChecklistItem",
    "ChecklistItemResult",
    "ConformanceGap",
    "Control",
    "ContractConformance",
    "DefinitionOfDone",
    "DeliveryActivity",
    "DeliveryArtifact",
    "DeliveryContract",
    "DeliveryInput",
    "DeliveryModel",
    "DeliveryOutput",
    "DeliveryPhase",
    "DeliveryProcess",
    "DeliveryTask",
    "EvidenceRequirement",
    "Methodology",
    "RaciAssignment",
    "Standard",
    "Template",
    "Waiver",
]
