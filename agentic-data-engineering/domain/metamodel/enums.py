"""Controlled vocabularies.

Enums live here when application code branches on them. Vocabularies that must
evolve *without* a code change -- capability catalogs, role catalogs,
relationship types, delivery process kinds, platform bindings -- live in
``metamodel-registry/*.yaml`` instead. See ADR-0002.
"""

from __future__ import annotations

from enum import StrEnum


class Twin(StrEnum):
    """Which dimension of the digital twin an entity belongs to.

    Both dimensions share one graph and one provenance model; this is a label
    for navigation and reporting, not a partition. See ADR-0008.
    """

    TECHNICAL = "TECHNICAL"
    DELIVERY = "DELIVERY"
    SHARED = "SHARED"


class EntityType(StrEnum):
    """Every entity type in the metamodel, across both twins.

    ``EntityRef`` and the relationship-type registry validate against this, so a
    typo in a reference or a registry file fails loudly instead of creating a
    dangling edge.
    """

    # --- Technical twin ---------------------------------------------------
    PROJECT = "Project"
    REPOSITORY = "Repository"
    CODE_ARTIFACT = "CodeArtifact"
    PIPELINE = "Pipeline"
    DATA_ASSET = "DataAsset"
    SCHEMA_DEFINITION = "SchemaDefinition"
    DATA_PROFILE = "DataProfile"
    INFRASTRUCTURE = "Infrastructure"
    CLOUD_RESOURCE = "CloudResource"
    ARCHITECTURE_ELEMENT = "ArchitectureElement"
    TEST = "Test"
    INCIDENT = "Incident"
    CHANGE = "Change"
    DEPLOYMENT = "Deployment"

    # --- Delivery twin ----------------------------------------------------
    DELIVERY_MODEL = "DeliveryModel"
    DELIVERY_PHASE = "DeliveryPhase"
    DELIVERY_TASK = "DeliveryTask"
    DELIVERY_ACTIVITY = "DeliveryActivity"
    DELIVERY_ARTIFACT = "DeliveryArtifact"
    DELIVERY_INPUT = "DeliveryInput"
    DELIVERY_OUTPUT = "DeliveryOutput"
    DELIVERY_PROCESS = "DeliveryProcess"
    DELIVERY_CONTRACT = "DeliveryContract"
    CHECKLIST = "Checklist"
    CHECKLIST_ITEM = "ChecklistItem"
    ACCEPTANCE_CRITERION = "AcceptanceCriterion"
    APPROVAL_GATE = "ApprovalGate"
    APPROVAL_RULE = "ApprovalRule"
    APPROVAL = "Approval"
    EVIDENCE_REQUIREMENT = "EvidenceRequirement"
    DEFINITION_OF_DONE = "DefinitionOfDone"
    STANDARD = "Standard"
    TEMPLATE = "Template"
    METHODOLOGY = "Methodology"
    CONTROL = "Control"
    RACI_ASSIGNMENT = "RaciAssignment"

    # --- Organization -----------------------------------------------------
    DELIVERY_ROLE = "DeliveryRole"
    ENGINEERING_RESPONSIBILITY = "EngineeringResponsibility"
    ENGINEERING_ROLE = "EngineeringRole"
    AGENT = "Agent"
    SKILL = "Skill"
    TOOL = "Tool"
    KNOWLEDGE_PACK = "KnowledgePack"
    POLICY = "Policy"

    # --- Problem and capability ------------------------------------------
    PROBLEM = "Problem"
    REQUIREMENT = "Requirement"
    CAPABILITY = "Capability"
    DELIVERY_CAPABILITY = "DeliveryCapability"
    CAPABILITY_GAP = "CapabilityGap"

    # --- Work -------------------------------------------------------------
    WORKFLOW = "Workflow"
    TASK = "Task"
    ARTIFACT = "Artifact"
    EVENT = "Event"
    DECISION = "Decision"
    OBSERVATION = "Observation"

    # --- Evaluation and evidence -----------------------------------------
    EVALUATION = "Evaluation"
    EVALUATION_SUITE = "EvaluationSuite"
    EVALUATION_SCENARIO = "EvaluationScenario"
    EVALUATION_METRIC = "EvaluationMetric"
    EVIDENCE = "Evidence"
    FINDING = "Finding"

    # --- Platform ---------------------------------------------------------
    PLATFORM = "Platform"
    TECHNOLOGY_BINDING = "TechnologyBinding"

    # --- Context engineering ----------------------------------------------
    MEMORY = "Memory"
    CONTEXT_POLICY = "ContextPolicy"
    CONTEXT_BUNDLE = "ContextBundle"
    CONTEXT_ITEM = "ContextItem"

    # --- Project graph (Phase 2) -------------------------------------------
    PROJECT_SNAPSHOT = "ProjectSnapshot"

    # --- Marketplace Foundry (Phase 10) -------------------------------------
    ENGINEERING_OBSERVATION = "EngineeringObservation"
    ENGINEERING_PATTERN = "EngineeringPattern"
    CANDIDATE_SKILL = "CandidateSkill"
    CANDIDATE_TOOL = "CandidateTool"
    CANDIDATE_AGENT = "CandidateAgent"


class ProvenanceState(StrEnum):
    """How a fact came to be believed. See ADR-0003."""

    OBSERVED = "OBSERVED"
    INFERRED = "INFERRED"
    HUMAN_VERIFIED = "HUMAN_VERIFIED"
    CERTIFIED = "CERTIFIED"


#: Provenance states a rule must reach before it is allowed to *block* delivery.
#: This is the addendum's "never silently convert inferred information into
#: certified organizational policy" expressed as data the validators consult.
BLOCKING_PROVENANCE: frozenset[ProvenanceState] = frozenset(
    {
        ProvenanceState.OBSERVED,
        ProvenanceState.HUMAN_VERIFIED,
        ProvenanceState.CERTIFIED,
    }
)


class ExtractionMethod(StrEnum):
    """How a delivery fact was obtained from a document.

    Delivery metadata is largely extracted from prose, so the extraction method
    travels with the fact: a heading match and an LLM reading of a paragraph
    warrant different scepticism.
    """

    DIRECT_DECLARATION = "DIRECT_DECLARATION"
    STRUCTURED_PARSE = "STRUCTURED_PARSE"
    PATTERN_MATCH = "PATTERN_MATCH"
    SEMANTIC_EXTRACTION = "SEMANTIC_EXTRACTION"
    HUMAN_ENTRY = "HUMAN_ENTRY"


class ActionClass(StrEnum):
    """Blast radius of one tool action. Required on every action."""

    READ_ONLY = "READ_ONLY"
    LOW_RISK_WRITE = "LOW_RISK_WRITE"
    HIGH_RISK_WRITE = "HIGH_RISK_WRITE"
    DESTRUCTIVE = "DESTRUCTIVE"


class RiskClass(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Severity(StrEnum):
    """Severity of an acceptance criterion or finding."""

    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ApprovalLevel(StrEnum):
    NONE = "NONE"
    SAMPLED_QA = "SAMPLED_QA"
    SINGLE_REVIEWER = "SINGLE_REVIEWER"
    MAKER_CHECKER = "MAKER_CHECKER"


class AutomationLevel(StrEnum):
    ASSISTED = "ASSISTED"
    SUPERVISED_AUTONOMOUS = "SUPERVISED_AUTONOMOUS"
    AUTONOMOUS = "AUTONOMOUS"


class AgentLifecycle(StrEnum):
    DRAFT = "DRAFT"
    CANDIDATE = "CANDIDATE"
    EVALUATED = "EVALUATED"
    CERTIFIED = "CERTIFIED"
    DEPLOYED = "DEPLOYED"
    MONITORED = "MONITORED"
    REEVALUATION_REQUIRED = "REEVALUATION_REQUIRED"
    DEPRECATED = "DEPRECATED"
    RETIRED = "RETIRED"


#: Legal agent lifecycle transitions. Anything absent is rejected at the
#: boundary rather than allowed to corrupt the audit trail.
AGENT_LIFECYCLE_TRANSITIONS: dict[AgentLifecycle, frozenset[AgentLifecycle]] = {
    AgentLifecycle.DRAFT: frozenset({AgentLifecycle.CANDIDATE, AgentLifecycle.RETIRED}),
    AgentLifecycle.CANDIDATE: frozenset(
        {AgentLifecycle.EVALUATED, AgentLifecycle.DRAFT, AgentLifecycle.RETIRED}
    ),
    AgentLifecycle.EVALUATED: frozenset(
        {AgentLifecycle.CERTIFIED, AgentLifecycle.CANDIDATE, AgentLifecycle.RETIRED}
    ),
    AgentLifecycle.CERTIFIED: frozenset({AgentLifecycle.DEPLOYED, AgentLifecycle.DEPRECATED}),
    AgentLifecycle.DEPLOYED: frozenset({AgentLifecycle.MONITORED, AgentLifecycle.DEPRECATED}),
    AgentLifecycle.MONITORED: frozenset(
        {AgentLifecycle.REEVALUATION_REQUIRED, AgentLifecycle.DEPRECATED}
    ),
    AgentLifecycle.REEVALUATION_REQUIRED: frozenset(
        {AgentLifecycle.EVALUATED, AgentLifecycle.DEPRECATED}
    ),
    AgentLifecycle.DEPRECATED: frozenset({AgentLifecycle.RETIRED}),
    AgentLifecycle.RETIRED: frozenset(),
}


class CandidateStatus(StrEnum):
    """Review progress of an unpublished marketplace candidate (Foundry).

    Deliberately NOT ``AgentLifecycle``: ``advance_agent()`` is structurally
    bound to a *registered* Agent's ``agent_key``, and ``Skill``/``Tool``
    have no lifecycle field at all. A candidate before publish has no
    registry identity, so it needs its own, smaller lifecycle.
    ``CERTIFIED`` is terminal here -- publish-to-YAML is a human act
    outside the system this phase builds.
    """

    CANDIDATE = "CANDIDATE"
    EVALUATED = "EVALUATED"
    CERTIFIED = "CERTIFIED"
    REJECTED = "REJECTED"


#: Legal candidate status transitions. Mirrors AGENT_LIFECYCLE_TRANSITIONS'
#: shape and purpose, deliberately smaller.
CANDIDATE_STATUS_TRANSITIONS: dict[CandidateStatus, frozenset[CandidateStatus]] = {
    CandidateStatus.CANDIDATE: frozenset({CandidateStatus.EVALUATED, CandidateStatus.REJECTED}),
    CandidateStatus.EVALUATED: frozenset(
        {CandidateStatus.CANDIDATE, CandidateStatus.CERTIFIED, CandidateStatus.REJECTED}
    ),
    CandidateStatus.CERTIFIED: frozenset(),
    CandidateStatus.REJECTED: frozenset(),
}


class DeploymentStage(StrEnum):
    CANDIDATE = "CANDIDATE"
    SHADOW = "SHADOW"
    CANARY = "CANARY"
    PRODUCTION = "PRODUCTION"


class ExecutionModel(StrEnum):
    """How an agent runs.

    EXTERNAL_AGENT is distinct from the other three: this platform does not
    run the loop and does not select a model for it -- execution happens
    entirely inside a third-party agent platform (e.g. GitHub Copilot coding
    agent). See ADR-0014 and Agent.external_provider.
    """

    SINGLE_SHOT = "SINGLE_SHOT"
    ITERATIVE = "ITERATIVE"
    PLANNER_EXECUTOR = "PLANNER_EXECUTOR"
    WORKFLOW_DRIVEN = "WORKFLOW_DRIVEN"
    EXTERNAL_AGENT = "EXTERNAL_AGENT"


class TestType(StrEnum):
    SCHEMA = "SCHEMA"
    DATA_QUALITY = "DATA_QUALITY"
    BUSINESS_RULE = "BUSINESS_RULE"
    RECONCILIATION = "RECONCILIATION"
    REGRESSION = "REGRESSION"
    PERFORMANCE = "PERFORMANCE"
    SECURITY = "SECURITY"
    LINEAGE = "LINEAGE"
    METADATA = "METADATA"
    CONTRACT = "CONTRACT"
    DEPLOYMENT = "DEPLOYMENT"


# --------------------------------------------------------------------------
# Delivery vocabularies
# --------------------------------------------------------------------------


class ChecklistItemStatus(StrEnum):
    """Outcome of one checklist item.

    ``WAIVED`` is not a synonym for ``NOT_APPLICABLE``: a waiver is a deliberate,
    attributed decision to proceed despite an unmet control, and carries an
    approver and evidence. Not-applicable means the control never applied.
    """

    PENDING = "PENDING"
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    WAIVED = "WAIVED"


class CompletionRule(StrEnum):
    """How item outcomes aggregate into a checklist outcome."""

    ALL = "ALL"
    ALL_MANDATORY = "ALL_MANDATORY"
    PERCENTAGE = "PERCENTAGE"


class GateStatus(StrEnum):
    """Readiness of an approval gate.

    ``CONDITIONAL`` exists because real gates are passed with conditions all the
    time; modelling only pass/fail would push that reality outside the system.
    """

    PASS = "PASS"
    CONDITIONAL = "CONDITIONAL"
    BLOCKED = "BLOCKED"


class GateDecision(StrEnum):
    """A human decision at a gate, as opposed to computed readiness."""

    APPROVE = "APPROVE"
    APPROVE_WITH_CONDITIONS = "APPROVE_WITH_CONDITIONS"
    REJECT = "REJECT"


class GateDimension(StrEnum):
    """The dimensions gate readiness is scored across."""

    ARTIFACTS = "ARTIFACTS"
    CHECKLISTS = "CHECKLISTS"
    EVALUATIONS = "EVALUATIONS"
    APPROVALS = "APPROVALS"
    EVIDENCE = "EVIDENCE"
    TRACEABILITY = "TRACEABILITY"


class RaciLetter(StrEnum):
    RESPONSIBLE = "RESPONSIBLE"
    ACCOUNTABLE = "ACCOUNTABLE"
    CONSULTED = "CONSULTED"
    INFORMED = "INFORMED"


class ValidationMethod(StrEnum):
    """How a checklist item or acceptance criterion is verified.

    ``AUTOMATED`` and ``METADATA_LOOKUP`` are machine-evaluable; the others need
    a human. Composition uses this to decide what an agent can actually
    discharge on its own.
    """

    AUTOMATED = "AUTOMATED"
    METADATA_LOOKUP = "METADATA_LOOKUP"
    TEST_EXECUTION = "TEST_EXECUTION"
    DOCUMENT_REVIEW = "DOCUMENT_REVIEW"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    PEER_REVIEW = "PEER_REVIEW"


#: Validation methods an agent can discharge without a human in the loop.
MACHINE_EVALUABLE: frozenset[ValidationMethod] = frozenset(
    {
        ValidationMethod.AUTOMATED,
        ValidationMethod.METADATA_LOOKUP,
        ValidationMethod.TEST_EXECUTION,
    }
)


# --------------------------------------------------------------------------
# Context engineering
# --------------------------------------------------------------------------


class MemoryScope(StrEnum):
    RUN = "RUN"
    TASK = "TASK"
    PROJECT = "PROJECT"
    AGENT = "AGENT"
    ORGANIZATION = "ORGANIZATION"


class TrustLevel(StrEnum):
    UNTRUSTED = "UNTRUSTED"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    AUTHORITATIVE = "AUTHORITATIVE"


TRUST_ORDER: dict[TrustLevel, int] = {
    TrustLevel.UNTRUSTED: 0,
    TrustLevel.LOW: 1,
    TrustLevel.MEDIUM: 2,
    TrustLevel.HIGH: 3,
    TrustLevel.AUTHORITATIVE: 4,
}


#: Total order over ApprovalLevel, so two independently-sourced levels (a
#: risk-matrix result and a ToolAction's own minimum_approval floor) can be
#: combined with max(). Mirrors TRUST_ORDER's shape and purpose exactly.
APPROVAL_ORDER: dict[ApprovalLevel, int] = {
    ApprovalLevel.NONE: 0,
    ApprovalLevel.SAMPLED_QA: 1,
    ApprovalLevel.SINGLE_REVIEWER: 2,
    ApprovalLevel.MAKER_CHECKER: 3,
}


class ContextItemKind(StrEnum):
    """What kind of thing a candidate context item is.

    The delivery kinds matter: an agent executing a DeliveryContract must be
    shown the checklist and acceptance criteria it will be judged against, and a
    policy can require exactly that.
    """

    # Technical
    KNOWLEDGE = "KNOWLEDGE"
    EVIDENCE = "EVIDENCE"
    MEMORY = "MEMORY"
    PROJECT_FACT = "PROJECT_FACT"
    POLICY = "POLICY"
    SCHEMA = "SCHEMA"
    CODE = "CODE"
    FINDING = "FINDING"
    # Delivery
    DELIVERY_STANDARD = "DELIVERY_STANDARD"
    CHECKLIST = "CHECKLIST"
    ACCEPTANCE_CRITERION = "ACCEPTANCE_CRITERION"
    GATE_RULE = "GATE_RULE"
    DELIVERY_TEMPLATE = "DELIVERY_TEMPLATE"


#: Item kinds that describe how work must be delivered rather than what is being
#: worked on. A DeliveryContract-aware policy treats these as mandatory.
DELIVERY_CONTEXT_KINDS: frozenset[ContextItemKind] = frozenset(
    {
        ContextItemKind.DELIVERY_STANDARD,
        ContextItemKind.CHECKLIST,
        ContextItemKind.ACCEPTANCE_CRITERION,
        ContextItemKind.GATE_RULE,
        ContextItemKind.DELIVERY_TEMPLATE,
    }
)


class OverflowStrategy(StrEnum):
    DROP_LOWEST_PRIORITY = "DROP_LOWEST_PRIORITY"
    TRUNCATE_LOWEST_PRIORITY = "TRUNCATE_LOWEST_PRIORITY"
    FAIL = "FAIL"


class DropReason(StrEnum):
    """Why a candidate did not make it into a bundle."""

    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    BELOW_TRUST_FLOOR = "BELOW_TRUST_FLOOR"
    STALE = "STALE"
    KIND_NOT_ALLOWED = "KIND_NOT_ALLOWED"
    MISSING_CITATION = "MISSING_CITATION"
    REDACTED = "REDACTED"
    DUPLICATE = "DUPLICATE"
