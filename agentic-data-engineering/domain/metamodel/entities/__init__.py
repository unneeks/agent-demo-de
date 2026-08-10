"""All concrete metamodel entities, across both twins.

``ENTITY_CLASSES`` is the single source schema export, registry validation and
the persistence adapters iterate. Nothing keeps a hand-maintained parallel list,
so adding an entity in one place is enough -- and forgetting to register one is
caught by a test that compares this mapping against ``EntityType``.
"""

from domain.metamodel.entities.delivery import (
    AcceptanceCriterion,
    Approval,
    ApprovalGate,
    ApprovalRule,
    Checklist,
    ChecklistItem,
    ChecklistItemResult,
    ConformanceGap,
    Control,
    ContractConformance,
    DefinitionOfDone,
    DeliveryActivity,
    DeliveryArtifact,
    DeliveryContract,
    DeliveryInput,
    DeliveryModel,
    DeliveryOutput,
    DeliveryPhase,
    DeliveryProcess,
    DeliveryTask,
    EvidenceRequirement,
    Methodology,
    RaciAssignment,
    Standard,
    Template,
    Waiver,
)
from domain.metamodel.entities.evaluation import (
    Evaluation,
    EvaluationMetric,
    EvaluationScenario,
    EvaluationSuite,
    Evidence,
    Finding,
    MetricResult,
)
from domain.metamodel.entities.foundry import (
    CandidateAgent,
    CandidateReview,
    CandidateSkill,
    CandidateTool,
    EngineeringObservation,
    EngineeringPattern,
)
from domain.metamodel.entities.organization import (
    Agent,
    DeliveryCapabilityDeclaration,
    DeliveryRole,
    EngineeringResponsibility,
    EngineeringRole,
    KnowledgePack,
    Policy,
    Skill,
    Tool,
    ToolAction,
)
from domain.metamodel.entities.shared import (
    Artifact,
    Capability,
    CapabilityGap,
    ContextBundle,
    ContextItem,
    ContextPolicy,
    Decision,
    DeliveryCapability,
    DroppedItem,
    Event,
    Memory,
    Observation,
    Platform,
    Problem,
    ProjectSnapshot,
    Requirement,
    Task,
    TechnologyBinding,
    Workflow,
)
from domain.metamodel.entities.technical import (
    ArchitectureElement,
    Change,
    CloudResource,
    CodeArtifact,
    DataAsset,
    DataProfile,
    Deployment,
    Incident,
    Infrastructure,
    Pipeline,
    Project,
    Repository,
    SchemaDefinition,
    Test,
)

_ALL_ENTITIES = (
    # Technical twin
    Project,
    Repository,
    CodeArtifact,
    Pipeline,
    DataAsset,
    SchemaDefinition,
    DataProfile,
    Infrastructure,
    CloudResource,
    ArchitectureElement,
    Test,
    Incident,
    Change,
    Deployment,
    # Delivery twin
    DeliveryModel,
    DeliveryPhase,
    DeliveryTask,
    DeliveryActivity,
    DeliveryArtifact,
    DeliveryInput,
    DeliveryOutput,
    DeliveryProcess,
    DeliveryContract,
    Checklist,
    ChecklistItem,
    AcceptanceCriterion,
    ApprovalGate,
    ApprovalRule,
    Approval,
    EvidenceRequirement,
    DefinitionOfDone,
    Standard,
    Template,
    Methodology,
    Control,
    RaciAssignment,
    # Organization
    DeliveryRole,
    EngineeringResponsibility,
    EngineeringRole,
    Agent,
    Skill,
    Tool,
    KnowledgePack,
    Policy,
    # Problem and capability
    Problem,
    Requirement,
    Capability,
    DeliveryCapability,
    CapabilityGap,
    # Work
    Workflow,
    Task,
    Artifact,
    Event,
    Decision,
    Observation,
    # Evaluation
    Evaluation,
    EvaluationSuite,
    EvaluationScenario,
    EvaluationMetric,
    Evidence,
    Finding,
    # Platform
    Platform,
    TechnologyBinding,
    # Context
    Memory,
    ContextPolicy,
    ContextBundle,
    ContextItem,
    # Project graph
    ProjectSnapshot,
    # Marketplace Foundry
    EngineeringObservation,
    EngineeringPattern,
    CandidateSkill,
    CandidateTool,
    CandidateAgent,
)

#: Every concrete entity class, keyed by its ``EntityType``.
ENTITY_CLASSES = {cls.model_fields["entity_type"].default: cls for cls in _ALL_ENTITIES}

#: Value objects that are part of the published contract but are not entities:
#: they have no independent identity and are always embedded in one.
VALUE_OBJECTS = {
    "Waiver": Waiver,
    "ChecklistItemResult": ChecklistItemResult,
    "ConformanceGap": ConformanceGap,
    "ContractConformance": ContractConformance,
    "DroppedItem": DroppedItem,
    "MetricResult": MetricResult,
    "ToolAction": ToolAction,
    "DeliveryCapabilityDeclaration": DeliveryCapabilityDeclaration,
    "CandidateReview": CandidateReview,
}

__all__ = [
    "ENTITY_CLASSES",
    "VALUE_OBJECTS",
    *sorted(cls.__name__ for cls in _ALL_ENTITIES),
    *sorted(VALUE_OBJECTS),
]
