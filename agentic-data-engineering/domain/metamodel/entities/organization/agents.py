"""Agent, Skill, Tool, KnowledgePack and Policy.

An Agent implements an EngineeringRole and is the replaceable part. Under the
addendum it must declare more than capability: it declares which parts of the
*organization's delivery model* it can actually perform (§13). "I can do data
modelling" is not a claim the composition engine can act on; "I can perform
task.logical-data-model, run its checklist and produce what
gate.data-architecture-review requires" is.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from domain.metamodel.base import EntityRef, MetamodelEntity, MetamodelModel
from domain.metamodel.enums import (
    AGENT_LIFECYCLE_TRANSITIONS,
    ActionClass,
    AgentLifecycle,
    ApprovalLevel,
    EntityType,
    ExecutionModel,
    RiskClass,
    TrustLevel,
    Twin,
)


class Skill(MetamodelEntity):
    """A reusable, independently testable unit of agent capability."""

    entity_type: EntityType = EntityType.SKILL
    twin: Twin = Twin.SHARED

    skill_key: str = Field(min_length=1)
    inputs: dict[str, str] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)
    preconditions: list[str] = Field(default_factory=list)
    postconditions: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    required_knowledge: list[str] = Field(default_factory=list)

    risk_level: RiskClass = RiskClass.LOW
    deterministic: bool = False
    idempotent: bool = True
    timeout_seconds: int = Field(default=300, gt=0)
    evaluation_suite_ref: EntityRef | None = None
    #: Checklist item keys this skill can discharge on its own. How an agent's
    #: delivery conformance is computed from the skills it holds.
    discharges_checklist_items: list[str] = Field(default_factory=list)


class ToolAction(MetamodelModel):
    """One callable operation on a tool.

    ``action_class`` has no default on purpose: an unclassified action cannot be
    constructed, so none can slip past an approval policy by omission.
    """

    name: str = Field(min_length=1)
    description: str | None = None
    action_class: ActionClass
    input_schema: dict[str, object] = Field(default_factory=dict)
    output_schema: dict[str, object] = Field(default_factory=dict)
    required_permissions: list[str] = Field(default_factory=list)
    minimum_approval: ApprovalLevel = ApprovalLevel.NONE
    rate_limit_per_minute: int | None = Field(default=None, gt=0)
    reversible: bool = True

    @model_validator(mode="after")
    def _dangerous_actions_need_approval(self) -> ToolAction:
        if (
            self.action_class in (ActionClass.HIGH_RISK_WRITE, ActionClass.DESTRUCTIVE)
            and self.minimum_approval is ApprovalLevel.NONE
        ):
            raise ValueError(
                f"action {self.name!r} is {self.action_class.value} and cannot have "
                "minimum_approval=NONE; high-risk and destructive actions always need a human."
            )
        return self


class Tool(MetamodelEntity):
    """An external executable capability the platform can invoke."""

    entity_type: EntityType = EntityType.TOOL
    twin: Twin = Twin.SHARED

    tool_key: str = Field(min_length=1)
    provider: str | None = None
    category: str | None = None
    platform_key: str | None = None
    actions: list[ToolAction] = Field(default_factory=list)

    authentication: str | None = Field(default=None, description="Mechanism, never a secret.")
    required_permissions: list[str] = Field(default_factory=list)
    cost_profile: str | None = None
    rate_limits: dict[str, int] = Field(default_factory=dict)
    security_constraints: list[str] = Field(default_factory=list)
    auditable: bool = True

    @property
    def max_action_class(self) -> ActionClass:
        """The most dangerous thing this tool can do."""
        order = [
            ActionClass.READ_ONLY,
            ActionClass.LOW_RISK_WRITE,
            ActionClass.HIGH_RISK_WRITE,
            ActionClass.DESTRUCTIVE,
        ]
        if not self.actions:
            return ActionClass.READ_ONLY
        return max((a.action_class for a in self.actions), key=order.index)

    def action(self, name: str) -> ToolAction | None:
        return next((a for a in self.actions if a.name == name), None)


class KnowledgePack(MetamodelEntity):
    """Explicit, versioned, citable knowledge.

    Knowledge lives here rather than inside prompts so an agent can cite what it
    used, and so correcting a standard is a data change rather than a prompt edit.
    """

    entity_type: EntityType = EntityType.KNOWLEDGE_PACK
    twin: Twin = Twin.SHARED

    knowledge_key: str = Field(min_length=1)
    scope: str | None = Field(default=None, description="enterprise | project | domain")
    source: str | None = None
    content_reference: str = Field(
        min_length=1, description="Pointer to the content -- not the content itself."
    )
    authority: str | None = None
    trust_level: TrustLevel = TrustLevel.MEDIUM
    freshness_days: int | None = Field(default=None, ge=0)
    index_reference: str | None = None
    #: Organizational learning (§29): incident patterns, recurring checklist
    #: failures, gate bottlenecks all become knowledge packs of this kind.
    knowledge_kind: str = Field(
        default="reference",
        description="reference | standard | historical_pattern | incident_lesson",
    )


class Policy(MetamodelEntity):
    """An executable governance rule."""

    entity_type: EntityType = EntityType.POLICY
    twin: Twin = Twin.SHARED

    policy_key: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    applies_to_action_classes: list[ActionClass] = Field(default_factory=list)
    required_approval: ApprovalLevel = ApprovalLevel.NONE
    enforcement: str = Field(default="blocking", description="blocking | advisory")
    rollback_strategy: str | None = None
    rationale: str | None = None


class DeliveryCapabilityDeclaration(MetamodelModel):
    """What an agent claims it can do within the organization's delivery model.

    The §13 addition. Without this an agent is a generic capability; with it, an
    agent is a candidate for specific organizational work, and the composition
    engine can reject it for reasons an engineering manager would recognise.
    """

    supported_phase_keys: list[str] = Field(default_factory=list)
    supported_task_keys: list[str] = Field(default_factory=list)
    supported_checklist_keys: list[str] = Field(default_factory=list)
    supported_artifact_kinds: list[str] = Field(default_factory=list)
    supported_gate_keys: list[str] = Field(default_factory=list)
    #: Evidence requirement keys this agent can produce evidence for.
    produces_evidence_keys: list[str] = Field(default_factory=list)


class Agent(MetamodelEntity):
    """One implementation of an EngineeringRole.

    Everything here is configuration, not code, so an agent version is fully
    described by its record and can be reproduced.
    """

    entity_type: EntityType = EntityType.AGENT
    twin: Twin = Twin.SHARED

    agent_key: str = Field(min_length=1)
    #: The engineering role this agent implements. The role outlives the agent.
    role_key: str = Field(min_length=1)
    mission: str | None = None

    capabilities: list[str] = Field(default_factory=list)
    delivery_capabilities: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    knowledge_packs: list[str] = Field(default_factory=list)
    policies: list[str] = Field(default_factory=list)

    #: What this agent can do inside the organization's delivery model.
    delivery: DeliveryCapabilityDeclaration = Field(
        default_factory=DeliveryCapabilityDeclaration
    )

    inputs: dict[str, str] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)

    # Runtime configuration. Provider and model stay free-form strings resolved
    # by the runtime, so no vendor is named in the domain.
    execution_model: ExecutionModel = ExecutionModel.PLANNER_EXECUTOR
    model_provider: str | None = None
    model_name: str | None = None
    model_configuration: dict[str, float | int | str | bool] = Field(default_factory=dict)

    #: When execution_model is EXTERNAL_AGENT, names the external system that
    #: owns execution end to end -- e.g. "github-copilot-coding-agent".
    #: Distinct from model_provider/model_name: those describe which LLM this
    #: platform's own runtime would call if it executed the agent itself, and
    #: do not apply when an external system owns the whole loop and this
    #: platform never picks a model. A mechanism identifier, never a
    #: credential (same convention as Tool.authentication). See ADR-0014.
    external_provider: str | None = None

    context_policy_ref: EntityRef | None = None
    memory_scopes: list[str] = Field(default_factory=list)
    planning_strategy: str | None = None
    delegation_strategy: str | None = None
    max_iterations: int = Field(default=10, gt=0)
    timeout_seconds: int = Field(default=900, gt=0)
    retry_policy: dict[str, int] = Field(default_factory=dict)

    human_approval_required: bool = True
    risk_class: RiskClass = RiskClass.MEDIUM
    cost_profile: str | None = None
    security_profile: str | None = None
    evaluation_suite_ref: EntityRef | None = None

    status: AgentLifecycle = AgentLifecycle.DRAFT
    certification_status: str | None = None

    @model_validator(mode="after")
    def _external_agent_needs_a_provider(self) -> Agent:
        if self.execution_model is ExecutionModel.EXTERNAL_AGENT and not self.external_provider:
            raise ValueError(
                f"agent {self.agent_key!r} has execution_model=EXTERNAL_AGENT but no "
                "external_provider; the platform must know which external system executes "
                "this role's work in order to attribute and govern what it produces."
            )
        return self

    def can_transition_to(self, target: AgentLifecycle) -> bool:
        return target in AGENT_LIFECYCLE_TRANSITIONS[self.status]

    def transition_to(self, target: AgentLifecycle) -> None:
        """Move along the lifecycle, rejecting illegal jumps.

        There is no path to DEPLOYED that bypasses CERTIFIED, and none back from
        RETIRED.
        """
        if not self.can_transition_to(target):
            allowed = sorted(t.value for t in AGENT_LIFECYCLE_TRANSITIONS[self.status])
            raise ValueError(
                f"illegal agent lifecycle transition {self.status.value} -> {target.value}; "
                f"allowed from {self.status.value}: {allowed or ['(terminal)']}"
            )
        self.status = target

    @property
    def is_deployable(self) -> bool:
        return self.status in (
            AgentLifecycle.CERTIFIED,
            AgentLifecycle.DEPLOYED,
            AgentLifecycle.MONITORED,
        )
